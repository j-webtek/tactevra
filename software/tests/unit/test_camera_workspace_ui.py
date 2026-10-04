"""Actual renderer in a finite DOM: navigation and saved-result GETs only.

The example records are explicitly fictional, not hardware/evidence acceptance.
No physical service, camera, serial provider, or original store is instantiated.
"""

from copy import deepcopy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import runpy
import shutil
import subprocess
from threading import Thread

import pytest

from test_arrival_wizard_device_selection_ui import _HARNESS, WORKSPACE
from rocell.application.camera_operating_evidence_preflight import CHECK_IDS
from rocell.application.camera_operating_proposal import FALSE_FIELDS


EXAMPLES = runpy.run_path(str(WORKSPACE / "software/scripts/camera_ui_preview.py"))


def render(*, full=None, target=None, load=False, refresh_status=None):
    node = shutil.which("node")
    assert node, "Node is required for the camera workspace UI acceptance tests"
    view, example = EXAMPLES["example_view"]()
    full = deepcopy(example if full is None else full)
    before = deepcopy(full)
    harness = (
        _HARNESS.replace(
            "function find(id)",
            """function matching(predicate) {
  const walk=node=>predicate(node)?node:node.children.map(walk).find(Boolean);
  return walk(find('#page-content'));
}
function attached(id){return matching(node=>node.id===id);}
const moves=[];
function find(id)""",
        )
        .replace(
            "global.document={querySelector:find,",
            "global.document={getElementById:attached,querySelector:find,",
        )
        .replace(
            "focus(){}",
            "focus(){document.activeElement=this;moves.push({kind:'focus',id:this.id||null});} scrollIntoView(){moves.push({kind:'scroll',id:this.id});}",
        )
        .replace(
            "if(path==='/api/view')",
            "if(path.startsWith('/api/operations/'))return{ok:true,json:async()=>input.full}; if(path==='/api/view')",
        )
        .replace(
            "if(input.prepare){",
            """if(input.target) {
    const link=matching(node=>node['data-camera-section']===input.target || (input.target==='camera-open-diagnostics' && node.id===input.target));
    if(!link)throw new Error('Missing shortcut');
    await link.listeners.click({preventDefault(){}});
  }
  if(input.load){
    const button=matching(node=>node.textContent==='Load assessment checklist');
    if(!button)throw new Error('Missing checklist loader');
    await button.listeners.click();
  }
  if(input.refreshStatus){
    input.snapshot.operations[0].status=input.refreshStatus;
    await find('#refresh-button').onclick();
  }
  if(input.prepare){""",
        )
        .replace(
            "process.stdout.write(JSON.stringify({requests,text:",
            """const checklists=[],disclosures=[];
  const walk=node=>{
    if(node.className==='camera-assessment')checklists.push(treeText(node));
    if(node.tagName==='DETAILS')disclosures.push({id:node.id||null,open:!!node.open,title:node.children[0]?.textContent});
    node.children.forEach(walk);
  };walk(find('#page-content'));
  process.stdout.write(JSON.stringify({requests,moves,checklists,disclosures,pageTitle:find('#page-title').textContent,text:""",
        )
    )
    result = subprocess.run(
        [node, "-e", harness],
        input=json.dumps(
            dict(
                script=(WORKSPACE / "software/src/rocell/ui/static/app.js").read_text(
                    encoding="utf-8"
                ),
                snapshot=view,
                page="camera",
                full=full,
                target=target,
                load=load,
                refreshStatus=refresh_status,
            )
        ),
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=8,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    page = json.loads(result.stdout)
    assert page["status"] == "Local service connected", page["error"]
    assert not page["dialogOpen"] and full == before
    assert all(request["method"] == "GET" for request in page["requests"])
    return page


def test_example_check_contract_tracks_the_production_assessor():
    assert EXAMPLES["CHECKS"] == CHECK_IDS
    assert EXAMPLES["FALSE_FIELDS"] == FALSE_FIELDS


def test_design_preview_only_serves_explicit_read_only_routes():
    # Loopback test server only. No wizard service or device provider is created.
    preview_handler = EXAMPLES["handler"]("incomplete")
    with ThreadingHTTPServer(
        ("127.0.0.1", 0), preview_handler
    ) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            for method, path, expected in [
                ("GET", "/", 200),
                ("GET", "/assets/app.js", 200),
                ("GET", "/assets/app.css", 200),
                ("GET", "/api/view", 200),
                ("GET", "/api/operations/" + EXAMPLES["OPERATION"], 200),
                ("POST", "/api/prepare", 405),
                ("POST", "/api/execute", 405),
                ("POST", "/api/export", 405),
                ("GET", "/../README.md", 404),
                ("GET", "/api/images/example", 404),
            ]:
                connection.request(method, path, headers={
                    "X-RoCell-Token": preview_handler.session_token,
                })
                response = connection.getresponse()
                data = response.read()
                assert response.status == expected
                if expected == 200:
                    assert response.getheader("Cache-Control") == "no-store"
                if path == "/":
                    assert b"FICTIONAL DATA - NO HARDWARE ACCESS" in data
            connection.close()
            guarded = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            guarded.request("GET", "/api/view")
            response = guarded.getresponse()
            assert response.status == 401
            response.read()
            guarded.request("GET", "/api/view", headers={
                "X-RoCell-Token": preview_handler.session_token,
                "Origin": "https://untrusted.example",
            })
            response = guarded.getresponse()
            assert response.status == 403
            response.read()
            guarded.close()
        finally:
            server.shutdown()
            thread.join(timeout=5)
            assert not thread.is_alive()


def test_landing_page_orders_guidance_image_activity_then_forms():
    page = render()
    text = page["text"]
    labels = [
        "Set up, inspect, then review",
        "Camera — next explicit step",
        "Retained camera image",
        "Recent activity",
        "Camera actions",
    ]
    assert [text.index(label) for label in labels] == sorted(
        text.index(label) for label in labels
    )
    assert len(page["requests"]) == 1 and not page["checklists"]
    assert "Assigned diagnostic folder" in text
    assert "Operating approval is still on hold" in text


@pytest.mark.parametrize(
    "target",
    ["camera-next-step", "camera-image", "camera-actions", "camera-detailed-records"],
)
def test_shortcuts_only_scroll_focus_or_expand(target):
    page = render(target=target)
    assert len(page["requests"]) == 1
    assert page["moves"][-2:] == [
        dict(kind="scroll", id=target),
        dict(
            kind="focus",
            id=target + "-summary" if target == "camera-detailed-records" else target,
        ),
    ]
    if target == "camera-detailed-records":
        assert next(row for row in page["disclosures"] if row["id"] == target)["open"]


def test_export_shortcut_only_opens_diagnostics_page():
    page = render(target="camera-open-diagnostics")
    assert page["pageTitle"] == "Diagnostics & exports"
    assert len(page["requests"]) == 1
    assert "No bundle exported yet" in page["text"]


@pytest.mark.parametrize("complete,count", [(True, 6), (False, 1)])
def test_explicit_result_load_shows_readable_historical_checks_without_approval(
    complete, count
):
    page = render(full=EXAMPLES["example_operation"](complete=complete), load=True)
    assert len(page["requests"]) == 2
    assert page["requests"][1]["path"] == "/api/operations/" + EXAMPLES["OPERATION"]
    (checklist,) = page["checklists"]
    assert f"{count} of 6 metadata checks satisfied" in checklist
    assert (
        "OPERATING APPROVAL HELD" in checklist and "Historical result only" in checklist
    )
    assert "7 remaining requirements" in checklist
    assert all(EXAMPLES["CHECKS"][i] not in checklist for i in range(6))
    assert "Installed focus, optics and placemat calibration are deferred" in checklist
    assert not next(
        row
        for row in page["disclosures"]
        if row["title"] == "Retained structured result"
    )["open"]


def invalid_results():
    paths = [
        (("status",), "FAILED"),
        (("status",), "CANCELLED"),
        (("completion_log_persisted",), False),
        (("result_retention",), "SUMMARY_ONLY"),
        (("result", "physical_authority"), True),
        (("result", "device_open_count"), 1),
        (("result", "steps"), []),
        (("result", "steps", 0, "name"), "other_report"),
        (("result", "steps", 0, "exit_code"), "0"),
    ]
    prefix = ("result", "steps", 0, "report")
    paths += [
        (prefix + path, value)
        for path, value in [
            (("schema",), "unknown"),
            (("physical_authority",), True),
            (("approved_operating_policy",), True),
            (("connected",), True),
            (("original_inputs_authenticated_at_read",), False),
            (("currentness_requires_revalidation",), False),
            (("unresolved_checks",), []),
            (("unresolved_checks",), ["unknown"]),
            (("preflight",), None),
            (("preflight", "checks"), None),
            (("preflight", "checks"), []),
            (("preflight", "checks", 0, "satisfied"), "true"),
            (("preflight", "checks", 0, "id"), "unknown_check"),
            (("preflight", "failed_checks"), []),
            (("preflight", "proposal_sha256"), "c" * 64),
            (("preflight", "status"), "CONSISTENT_METADATA_PENDING_ORIGINAL_REVIEW"),
        ]
    ]
    paths += [(prefix + ("preflight", field), True) for field in FALSE_FIELDS]
    for path, value in paths:
        operation = EXAMPLES["example_operation"]()
        destination = operation
        for key in path[:-1]:
            destination = destination[key]
        destination[path[-1]] = value
        yield pytest.param(operation, id="-".join(map(str, path)))


@pytest.mark.parametrize("full", list(invalid_results()))
def test_malformed_partial_or_authority_bearing_results_show_no_passes(full):
    page = render(full=full, load=True)
    (checklist,) = page["checklists"]
    assert "Checklist unavailable" in checklist
    assert "metadata checks satisfied" not in checklist
    assert "OPERATING APPROVAL HELD" in checklist


@pytest.mark.parametrize("field", ["operation_id", "action_id"])
def test_result_from_another_operation_is_not_displayed(field):
    full = EXAMPLES["example_operation"]()
    full[field] = "wrong-result"
    page = render(full=full, load=True)
    assert not page["checklists"]
    assert "does not match this operation" in page["error"]


def test_refresh_retains_historical_report_without_reloading_it():
    page = render(load=True, refresh_status="SUCCEEDED")
    assert len(page["requests"]) == 3
    assert len(page["checklists"]) == 1
    assert "Historical result only" in page["checklists"][0]


def test_status_change_does_not_reuse_a_previously_loaded_checklist():
    page = render(load=True, refresh_status="FAILED")
    assert len(page["requests"]) == 3 and not page["checklists"]
    assert "Assessment is incomplete or held" in page["text"]
