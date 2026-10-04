"""Actual Control Center renderer and existing form navigation, no device IO.

The finite DOM checks attached controls, modeled user input and exact requests.
The catalog comes from existing ActionDefinitions or the real cached service view.
No UI navigation may prepare/execute an action or infer hardware qualification.
"""

from copy import deepcopy
import json
import runpy
import shutil
import subprocess

import pytest

from rocell.application.wizard_actions import ACTIONS
from test_arrival_wizard_device_selection_ui import _HARNESS, WORKSPACE
from test_arrival_wizard_service import make_service
from test_wizard_camera_next_step_ui import fresh, offered


def render(actions=(), *, steps=(), view=None):
    assert shutil.which("node"), "Node is required for Control Center tests"
    snapshot = deepcopy(fresh(list(actions)) if view is None else view)
    original = deepcopy(snapshot)
    harness = (
        _HARNESS.replace(
            "append(...items){this.children.push(...items);} replaceChildren(...items){this.children=items;}",
            "append(...items){for(const item of items)item.parentElement=this;this.children.push(...items);} replaceChildren(...items){for(const child of this.children)child.parentElement=null;this.children=[];this.append(...items);}",
        )
        .replace(
            "function find(id)",
            """function matching(predicate) {
  const walk=node=>predicate(node)?node:node.children.map(walk).find(Boolean);
  return walk(find('#page-content'));
}
function attached(id){return matching(node=>node.id===id);}
const observations=[],moves=[];
function find(id)""",
        )
        .replace(
            "global.document={querySelector:find,",
            "global.document={getElementById:attached,createElementNS:(_,tag)=>new Element(tag),querySelector:find,",
        )
        .replace(
            "focus(){}",
            "focus(){document.activeElement=this;moves.push({kind:'focus',id:this.id||null});} scrollIntoView(){moves.push({kind:'scroll',id:this.id});}",
        )
        .replace(
            "if(input.prepare){",
            """const oldButtons=new Map();
  function observe(){
    const rows=[],forms=[];
    const walk=(node,visible=true)=>{
      if(node['data-catalog-action'])rows.push({id:node['data-catalog-action'],text:textOf(node),
        disabled:node.children.find(child=>child['data-open-control'])?.disabled});
      if(node.tagName==='FORM')forms.push({id:node.parentElement.id,visible,
        disabled:node.children.find(child=>child.type==='submit')?.disabled});
      for(const child of node.children)walk(child,visible&&(node.tagName!=='DETAILS'||node.open||child.tagName==='SUMMARY'));
    };walk(find('#page-content'));
    observations.push({rows,forms,status:attached('control-results-status')?.textContent||null,
      page:find('#page-title').textContent,query:attached('control-search')?.value,
      controls:nodes.filter(node=>node.id?.startsWith('field-')&&attached(node.id)===node).map(node=>({id:node.id,value:node.value,checked:!!node.checked})),
      error:find('#error-banner').textContent});
  }
  function textOf(node){return [node.textContent,...node.children.map(textOf)].join('\\n');}
  observe();
  for(const step of input.steps){
    if(step.field){const field=attached(step.field);field.value=step.value;await field.listeners[step.field==='control-search'?'input':'change']();}
    if(step.button){const button=matching(node=>node.textContent===step.button&&node.tagName==='BUTTON');if(!button)throw Error('No button');if(!button.disabled)await button.listeners.click();}
    if(step.save){oldButtons.set(step.save,matching(node=>node['data-open-control']===step.save));}
    if(Object.hasOwn(step,'catalog')){input.snapshot.actions=step.catalog;await find('#refresh-button').onclick();}
    if(step.refresh)await find('#refresh-button').onclick();
    if(step.page)find('#navigation').listeners.click({target:{closest:()=>({dataset:{page:step.page}})}});
    if(step.open){const button=matching(node=>node['data-open-control']===step.open);if(!button)throw Error('No open control');await button.listeners.click();}
    if(step.stale)await oldButtons.get(step.stale).listeners.click();
    if(step.submit){
      const box=attached(step.submit);const form=box.children.find(node=>node.tagName==='FORM');
      await form.listeners.submit({preventDefault(){}});
    }
    observe();
  }
  if(input.prepare){""",
        )
        .replace(
            "JSON.stringify({requests,text:",
            "JSON.stringify({requests,observations,moves,text:",
        )
    )
    result = subprocess.run(
        [shutil.which("node"), "-e", harness],
        input=json.dumps(
            dict(
                script=(WORKSPACE / "software/src/rocell/ui/static/app.js").read_text(
                    encoding="utf-8"
                ),
                snapshot=snapshot,
                page="controls",
                steps=steps,
            )
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    page = json.loads(result.stdout)
    assert page["status"] == "Local service connected", page["error"]
    assert snapshot == original
    return page


def read_only(page):
    assert all(
        row == dict(path="/api/view", method="GET", body=None)
        for row in page["requests"]
    )
    assert not page["dialogOpen"]


def test_registered_catalog_is_complete_across_all_pages():
    catalog = [action.view(mode="rehearsal", busy=False) for action in ACTIONS]
    page = render(
        catalog, steps=[dict(button="Next controls")] * ((len(catalog) - 1) // 12)
    )
    read_only(page)
    rows = [row for observation in page["observations"] for row in observation["rows"]]
    assert len(rows) == len(ACTIONS) == len({row["id"] for row in rows})
    assert {row["id"] for row in rows} == {action.action_id for action in ACTIONS}
    assert not any(row["disabled"] for row in rows)
    assert "not hardware-ready" in page["text"]


def test_read_only_preview_has_every_definition_but_no_enabled_actions():
    preview = runpy.run_path(str(WORKSPACE / "software/scripts/camera_ui_preview.py"))
    view, _ = preview["example_view"]("catalog")
    assert {row["action_id"] for row in view["actions"]} == {
        action.action_id for action in ACTIONS
    }
    assert all(row["enabled"] is False for row in view["actions"])
    assert view["operations"] == [] and view["physical_authority"] is False


def test_every_registered_action_opens_its_original_form():
    catalog = [action.view(mode="rehearsal", busy=False) for action in ACTIONS]
    steps = []
    for action in ACTIONS:
        steps.extend(
            [
                dict(field="control-search", value=action.action_id),
                dict(open=action.action_id),
                dict(page="controls"),
            ]
        )
    page = render(catalog, steps=steps)
    read_only(page)
    for index, action in enumerate(ACTIONS):
        opened = page["observations"][2 + index * 3]
        matches = [
            row
            for row in opened["forms"]
            if row["id"] == f"{action.section}-action-{action.action_id}"
        ]
        assert len(matches) == 1 and matches[0]["visible"], action.action_id
        assert not opened["error"], action.action_id


def test_real_initial_service_catalog_has_no_missing_or_unroutable_controls(
    make_service,
):
    service, _, _ = make_service(mode="physical")
    view = service.view()
    page = render(
        view=view,
        steps=[dict(button="Next controls")] * ((len(view["actions"]) - 1) // 12),
    )
    read_only(page)
    rows = [row for observation in page["observations"] for row in observation["rows"]]
    assert {row["id"] for row in rows} == {row["action_id"] for row in view["actions"]}
    assert not any(row["disabled"] for row in rows)


@pytest.mark.parametrize(
    "section",
    ["camera", "arm", "board", "tasks", "overview", "commissioning", "diagnostics"],
)
def test_open_routes_to_existing_form_without_prepare_or_execute(section):
    action = offered("example_action", section=section)
    page = render([action], steps=[dict(open=action["action_id"])])
    read_only(page)
    assert page["observations"][-1]["forms"] == [
        dict(id=section + "-action-example_action", visible=True, disabled=False)
    ]
    assert page["moves"][-1] == dict(
        kind="focus", id=section + "-action-example_action"
    )


def test_held_camera_form_is_expanded_but_cannot_preview():
    action = dict(
        offered("held_camera", enabled=False),
        blocked_reasons=["Received calibration pending"],
    )
    page = render(
        [action],
        steps=[dict(open="held_camera"), dict(submit="camera-action-held_camera")],
    )
    read_only(page)
    assert page["observations"][-1]["forms"] == [
        dict(id="camera-action-held_camera", visible=True, disabled=True)
    ]
    assert "Received calibration pending" in page["text"]


def test_selected_evidence_and_consent_are_not_filled_by_navigation():
    action = dict(
        offered("review_camera"),
        fields=[
            dict(
                name="candidate",
                type="select",
                required=True,
                options=[dict(value="one", label="One device")],
            ),
            dict(name="confirm", type="checkbox", required=True, default=False),
        ],
    )
    page = render([action], steps=[dict(open="review_camera")])
    read_only(page)
    assert all(
        row["value"] == "" and row["checked"] is False
        for row in page["observations"][-1]["controls"]
    )


def test_open_then_explicit_preview_uses_existing_ticket_boundary():
    page = render(
        [offered("example_action")],
        steps=[
            dict(open="example_action"),
            dict(submit="camera-action-example_action"),
        ],
    )
    assert page["requests"] == [
        dict(path="/api/view", method="GET", body=None),
        dict(
            path="/api/prepare",
            method="POST",
            body=dict(action_id="example_action", input={}, expected_revision=7),
        ),
    ]
    assert page["dialogOpen"] is True


def test_search_filters_hold_reasons_and_clear_restores_all_controls():
    first = dict(
        offered("camera_one", enabled=False),
        blocked_reasons=["Distinct serial identity needs review"],
    )
    second = offered("arm_one", section="arm")
    page = render(
        [first, second],
        steps=[
            dict(field="control-search", value="SERIAL IDENTITY"),
            dict(field="control-availability", value="offered"),
            dict(button="Clear filters"),
            dict(field="control-section", value="arm"),
        ],
    )
    read_only(page)
    assert [
        [row["id"] for row in observation["rows"]]
        for observation in page["observations"]
    ] == [
        ["camera_one", "arm_one"],
        ["camera_one"],
        [],
        ["camera_one", "arm_one"],
        ["arm_one"],
    ]


def test_phone_search_finds_existing_task_options_without_selecting_phone():
    catalog = [action.view(mode="rehearsal", busy=False) for action in ACTIONS]
    page = render(
        catalog,
        steps=[dict(field="control-search", value="phone"), dict(open="plan_task")],
    )
    read_only(page)
    assert {row["id"] for row in page["observations"][1]["rows"]} >= {
        "plan_task",
        "simulate_task",
    }
    device = next(
        row
        for row in page["observations"][-1]["controls"]
        if row["id"] == "field-plan_task-device"
    )
    assert device["value"] == "keyboard"  # Existing default, not the searched target.


def test_search_does_not_index_default_operator_values():
    action = dict(
        offered("example"),
        fields=[dict(name="operator", type="text", default="PRIVATE_DEFAULT_SENTINEL")],
    )
    page = render(
        [action], steps=[dict(field="control-search", value="PRIVATE_DEFAULT_SENTINEL")]
    )
    read_only(page)
    assert page["observations"][-1]["rows"] == []


@pytest.mark.parametrize("invalid", [None, {}, "true", 1])
def test_non_boolean_availability_is_unroutable(invalid):
    page = render([offered("ambiguous", enabled=invalid)])
    read_only(page)
    assert page["observations"][0]["rows"][0]["disabled"] is True


@pytest.mark.parametrize(
    "catalog",
    [
        None,
        {},
        [None],
        [dict(offered("wrong"), section="unmapped")],
        [dict(offered("bad_fields"), fields=[None])],
        [offered("duplicate"), offered("duplicate")],
        [offered("large")] * 513,
    ],
)
def test_malformed_or_ambiguous_catalog_does_not_invent_controls(catalog):
    page = render(steps=[dict(catalog=catalog)])
    read_only(page)
    assert all(row["disabled"] for row in page["observations"][-1]["rows"])
    assert any(
        word in page["text"].lower()
        for word in ("unsupported", "ambiguous", "supported display limit")
    )


def test_stale_directory_button_rechecks_current_catalog():
    page = render(
        [offered("removed")],
        steps=[dict(save="removed"), dict(catalog=[]), dict(stale="removed")],
    )
    read_only(page)
    assert "no longer uniquely available" in page["error"]


def test_search_state_survives_navigation_and_refresh_without_retaining_form_inputs():
    page = render(
        [offered("camera_one"), offered("camera_two")],
        steps=[
            dict(field="control-search", value="camera_two"),
            dict(page="camera"),
            dict(page="controls"),
            dict(refresh=True),
        ],
    )
    read_only(page)
    assert page["observations"][-1]["query"] == "camera_two"
    assert [row["id"] for row in page["observations"][-1]["rows"]] == ["camera_two"]
