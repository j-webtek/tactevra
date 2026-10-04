"""Check local file links in maintained entry docs, not archived lab records.

Checks this repository's issue-template URLs against local template files too.
Also enforces explicit public-page titles and required navigation routes.
Only explicitly listed plain-heading anchors are checked; this is not a general
Markdown parser, URL reachability check, or visual review.
"""
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
DOCS = (
    'README.md', 'PROJECT_STATUS.md', 'ROADMAP.md', 'CONTRIBUTING.md', 'SUPPORT.md', 'SECURITY.md',
    'GOVERNANCE.md',
    'THIRD_PARTY_NOTICES.md',
    'CODE_OF_CONDUCT.md',
    'docs/README.md', 'docs/GETTING_STARTED.md', 'docs/RELEASING.md',
    'docs/releases/README.md', 'docs/releases/READINESS.md',
    'docs/SYSTEM_OVERVIEW.md', 'docs/GLOSSARY.md',
    'docs/HARDWARE_BUILD_GUIDE.md',
    'docs/DOCUMENTATION_STANDARD.md',
    'docs/EVIDENCE_RETENTION.md',
    'docs/ARTIFACT_GOVERNANCE.md',
    'docs/SOURCE_DISTRIBUTION.md',
    'docs/releases/EXPERIMENTAL_PREVIEW_DRAFT.md',
    'docs/releases/CANDIDATE_DCD87DB.md',
    'docs/releases/CANDIDATE_ED29E82F.md',
    'docs/releases/TACTEVRA_V0.1.0_ALPHA.1_NOTES.md',
    'docs/releases/BASELINE_2026-09-26.md',
    'docs/releases/NEWCOMER_CHECK_2026-09-26.md',
    'docs/releases/COMPATIBILITY_CONTENT_REVIEW_2026-09-26.md',
    'docs/HARDWARE_PROVENANCE.md',
    'docs/REPOSITORY_OPERATIONS.md',
    'docs/MAINTAINER_CHECKLIST.md',
    'docs/decisions/README.md',
    'docs/CI.md', 'docs/AUDIT_FIXTURE_REVIEW.md', 'software/README.md',
    'software/RUNTIME_IMPLEMENTATION_HISTORY.md', 'software/ai/README.md',
    'software/ai/docs/README.md', 'assets/brand/README.md',
    'software/ai/docs/CONTRACT.md',
    'software/ai/docs/SHARED_AI_ARM_WORKPLAN.md',
    'software/ai/docs/EVIDENCE_LEDGER.md',
    'software/docs/ARCHITECTURE.md',
    'software/docs/AI_TO_ARM_OPERATIONAL_EFFICIENCY_PLAN.md',
    'software/docs/ISAAC_SIM_INTEGRATION_PLAN.md',
    'software/integrations/isaac_sim/README.md',
    'docs/brand/BRAND_GUIDE.md', 'docs/brand/NAMING_REVIEW.md',
    'docs/brand/MIGRATION_PLAN.md',
    'assets/media/README.md', 'assets/media/VERIFICATION_RECEIPT.md',
)

# Deliberately narrow: compatibility identifiers and historical records are not
# subject to brand-name replacement. Update this contract with intentional UI changes.
PUBLIC_TITLES = {
    'README.md': 'Tactevra',
    'PROJECT_STATUS.md': 'Tactevra project status',
    'ROADMAP.md': 'Tactevra roadmap',
    'CONTRIBUTING.md': 'Contributing to Tactevra',
    'SUPPORT.md': 'Getting help with Tactevra',
    'SECURITY.md': 'Tactevra security reporting',
    'CODE_OF_CONDUCT.md': 'Tactevra community code of conduct',
    'THIRD_PARTY_NOTICES.md': 'Tactevra third-party notices',
    'GOVERNANCE.md': 'Tactevra project governance',
    'docs/README.md': 'Tactevra documentation',
    'docs/GETTING_STARTED.md': 'Getting started with Tactevra',
    'docs/SYSTEM_OVERVIEW.md': 'Tactevra system overview',
    'docs/GLOSSARY.md': 'Tactevra glossary',
    'docs/HARDWARE_BUILD_GUIDE.md': 'Building the Tactevra RC03 workcell',
    'docs/decisions/README.md': 'Tactevra decision records',
    'docs/DOCUMENTATION_STANDARD.md': 'Tactevra documentation standard',
    'docs/SOURCE_DISTRIBUTION.md': 'Tactevra source-distribution footprint',
    'docs/releases/READINESS.md': 'Tactevra experimental-preview readiness',
    'software/README.md': 'Tactevra Runtime',
    'software/RUNTIME_IMPLEMENTATION_HISTORY.md': 'Tactevra Runtime implementation history',
    'software/ai/README.md': 'Tactevra AI',
    'software/ai/docs/CONTRACT.md': 'AI-to-Tactevra Runtime integration contract',
    'software/ai/docs/SHARED_AI_ARM_WORKPLAN.md': 'Shared AI-to-arm workplan',
    'software/ai/docs/EVIDENCE_LEDGER.md': 'Tactevra AI/arm evidence ledger',
    'software/docs/ARCHITECTURE.md': 'Tactevra Runtime software architecture',
    'software/docs/ISAAC_SIM_INTEGRATION_PLAN.md': 'Tactevra Isaac Sim integration plan',
    'software/integrations/isaac_sim/README.md': 'Isaac Sim integration boundary',
    'assets/media/VERIFICATION_RECEIPT.md': 'Tactevra overview-media verification receipt',
}

REQUIRED_PHRASES = {
    'GOVERNANCE.md': (
        '**Document status:** Current governance policy',
        '**Authority:** Repository decision process only.',
        '[decision-record index](docs/decisions/README.md)',
    ),
    'docs/decisions/README.md': (
        '**Document status:** Current decision-process index',
        '**Authority:** Documentation and traceability only;',
        '[the template](TEMPLATE.md)',
        '[0001 — Waveshare model license disposition](0001-waveshare-model-license-disposition.md)',
    ),
    'ROADMAP.md': (
        '**Document status:** Current public roadmap',
        '**Authority:** Planning and navigation only.',
        '[project status](PROJECT_STATUS.md)',
        'https://github.com/j-webtek/tactevra/issues/88',
        'https://github.com/j-webtek/tactevra/issues/167',
    ),
    'docs/SYSTEM_OVERVIEW.md': (
        '**Document status:** Current overview',
        '**Authority:** Explanatory; it does not authorize hardware operation',
    ),
    'docs/GLOSSARY.md': ('**Document status:** Current reference',),
    'docs/HARDWARE_BUILD_GUIDE.md': (
        '**Document status:** Current builder guide',
        '**Authority:** Explanatory; controlled RC03 records determine print and build eligibility',
        '| Powered robot motion | **Not authorized** |',
    ),
    'docs/DOCUMENTATION_STANDARD.md': ('**Document status:** Current policy',),
    'docs/ARTIFACT_GOVERNANCE.md': (
        '**Document status:** Current repository policy',
        '**Authority:** Repository placement and reviewability only;',
    ),
    'docs/SOURCE_DISTRIBUTION.md': (
        '**Document status:** Current repository policy',
        '**Authority:** Repository packaging and clone-cost guidance only.',
        'GitHub-generated source archives',
        'release-readiness.json',
        'inventory_source_archive_duplicates.py',
        'https://github.com/j-webtek/tactevra/issues/56',
        'https://github.com/j-webtek/tactevra/issues/61',
        'decisions/0001-waveshare-model-license-disposition.md',
        'https://github.com/j-webtek/tactevra/issues/167',
    ),
    'THIRD_PARTY_NOTICES.md': (
        '**Document status:** Current attribution index',
        '**Authority:** Informational inventory only.',
        '**upstream-declared MIT; complete notice and scope unconfirmed**',
    ),
    'docs/releases/README.md': (
        '**Document status:** Current release index',
        '**Authority:** Navigation and readiness context only; this page does not approve or publish a release',
        'https://github.com/j-webtek/tactevra/issues/57',
    ),
    'docs/releases/READINESS.md': (
        '**Document status:** Current release-readiness dashboard',
        '**Authority:** Status and routing only; this page does not approve publication or authorize hardware operation',
        '**Selected and technically qualified**',
        '**Not approved or published**',
        'https://github.com/j-webtek/tactevra/issues/56',
        'https://github.com/j-webtek/tactevra/issues/61',
        'https://github.com/j-webtek/tactevra/issues/88',
        'https://github.com/j-webtek/tactevra/issues/167',
    ),
    'software/RUNTIME_IMPLEMENTATION_HISTORY.md': (
        '**Document status:** Historical evidence index',
        '**Authority:** Historical context only; it does not authorize hardware operation',
    ),
    'software/README.md': (
        '**Document status:** Current software reference',
        '**Authority:** Explanatory; this page does not authorize hardware operation',
    ),
    'software/ai/README.md': (
        '**Document status:** Current research and integration reference',
        '**Authority:** Research guidance only; this page grants no controller authority',
    ),
    'software/ai/docs/SHARED_AI_ARM_WORKPLAN.md': (
        '**Status:** active coordination document',
        '[Tactevra AI/arm evidence ledger](EVIDENCE_LEDGER.md)',
    ),
    'software/ai/docs/EVIDENCE_LEDGER.md': (
        '**Document status:** Append-only evidence record',
        'duplicate `E-20260926-INT-001` identifier',
    ),
    'software/docs/ISAAC_SIM_INTEGRATION_PLAN.md': (
        '**Document status:** Active integration plan',
        '**Authority:** Planning and software-test guidance only.',
        'hardware_access=false',
        'physical_authority=false',
        'no simulator result can promote a physical hardware gate',
    ),
    'software/integrations/isaac_sim/README.md': (
        '**Document status:** Active implementation reference',
        '**Authority:** Software-test guidance only;',
        'CONTRACT_TEST_ONLY',
        'UNSELECTED',
    ),
    'assets/media/VERIFICATION_RECEIPT.md': (
        '**Document status:** Current published-media verification',
        '**Authority:** Byte identity and post-merge inspection only;',
        'decision 0001',
        'not a Blender rerender',
        'does not qualify robot motion',
    ),
    'docs/releases/EXPERIMENTAL_PREVIEW_DRAFT.md': (
        '**Status:** Superseded preparation record; unpublished',
        'https://github.com/j-webtek/tactevra/issues/57',
    ),
    'docs/releases/CANDIDATE_DCD87DB.md': (
        '**Disposition: SUPERSEDED WITHOUT PUBLICATION.**',
    ),
    'docs/releases/CANDIDATE_ED29E82F.md': (
        '**Disposition: TECHNICALLY QUALIFIED; PUBLICATION NOT APPROVED.**',
        'ed29e82fcebbd3fe4194fa141d0eaadc3c3c8fc3',
        'https://github.com/j-webtek/tactevra/actions/runs/37175363712',
    ),
}

# (relative Markdown destination, optional exact plain ATX heading).
PUBLIC_ROUTES = {
    'README.md': (
        ('docs/GETTING_STARTED.md#install-the-software', 'Install the software'),
        ('docs/SYSTEM_OVERVIEW.md', None),
        ('docs/HARDWARE_BUILD_GUIDE.md', None),
        ('PROJECT_STATUS.md', None), ('ROADMAP.md', None), ('docs/README.md', None),
        ('SUPPORT.md', None), ('SECURITY.md', None),
        ('GOVERNANCE.md', None),
        ('THIRD_PARTY_NOTICES.md', None),
    ),
    'docs/README.md': (
        ('GETTING_STARTED.md', None), ('../PROJECT_STATUS.md', None),
        ('../ROADMAP.md', None),
        ('SYSTEM_OVERVIEW.md', None), ('GLOSSARY.md', None),
        ('HARDWARE_BUILD_GUIDE.md', None),
        ('releases/READINESS.md', None), ('releases/README.md', None),
        ('../SUPPORT.md', None), ('../CONTRIBUTING.md', None),
        ('../GOVERNANCE.md', None),
        ('../SECURITY.md', None), ('../CODE_OF_CONDUCT.md', None),
        ('../THIRD_PARTY_NOTICES.md', None),
    ),
    'SUPPORT.md': (
        ('docs/GETTING_STARTED.md#what-you-can-do-today', 'What you can do today'),
        ('SECURITY.md', None), ('CODE_OF_CONDUCT.md', None),
        ('GOVERNANCE.md', None),
        ('CONTRIBUTING.md#export-sharing', 'Export sharing'),
    ),
    'docs/GETTING_STARTED.md': (
        ('../PROJECT_STATUS.md', None), ('../CONTRIBUTING.md', None),
    ),
    'docs/HARDWARE_BUILD_GUIDE.md': (
        ('../PROJECT_STATUS.md', None), ('../SUPPORT.md', None),
        ('../CONTRIBUTING.md', None),
        ('../active-project/RoCell_v0_3/README_FIRST.md', None),
        ('../active-project/RoCell_v0_3/PRINT_READINESS.md', None),
        ('../active-project/RoCell_v0_3/PREHARDWARE_READINESS.md', None),
        ('../active-project/RoCell_v0_3/BUILD_TRACKER.md', None),
        ('../active-project/RoCell_v0_3/BUILD_BY_STEP/README.md', None),
    ),
}


def without_fences(content: str) -> str:
    """Exclude backtick/tilde fenced examples from the small entry-doc checks."""
    lines = []
    fence = None
    for line in content.splitlines():
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if (marker and marker[1][0] == fence[0]
                    and len(marker[1]) >= len(fence) and not marker[2].strip()):
                fence = None
            continue
        if marker:
            fence = marker[1]
        else:
            lines.append(line)
    return '\n'.join(lines)


def public_entry_errors(relative: str, content: str, root: Path) -> list[str]:
    """Enforce the reviewed entry-page contract without inspecting runtime code."""
    content = without_fences(content)
    errors = []
    title = PUBLIC_TITLES.get(relative)
    headings = re.findall(r'^# +(.+?)\s*$', content, flags=re.M)
    if title and headings != [title]:
        errors.append(f'expected one public title: # {title}')
    for phrase in REQUIRED_PHRASES.get(relative, ()):
        if phrase not in content:
            errors.append(f'missing required status context: {phrase}')
    links = {target.strip().strip('<>')
             for target in re.findall(r'\]\(([^)]+)\)', content)}
    for target, heading in PUBLIC_ROUTES.get(relative, ()):
        if target not in links:
            errors.append(f'missing required navigation link: {target}')
        destination = root / Path(relative).parent / urlsplit(target).path
        if not destination.is_file():
            errors.append(f'missing navigation destination: {target}')
            continue
        if heading:
            # Only plain headings explicitly listed above; no inferred GitHub slugger.
            fragment = urlsplit(target).fragment
            if fragment != heading.lower().replace(' ', '-'):
                errors.append(f'invalid navigation anchor contract: {target}')
            headings_at_target = re.findall(
                r'^#{1,6} +(.+?)\s*$',
                without_fences(destination.read_text(encoding='utf-8')), flags=re.M)
            if headings_at_target.count(heading) != 1:
                errors.append(f'expected one navigation heading "{heading}" in {target}')
    return errors


def issue_template_error(target: str, root: Path) -> str | None:
    """Check only this repository's template links, without network requests."""
    parsed = urlsplit(target)
    if (parsed.netloc.lower() != 'github.com'
            or parsed.path.rstrip('/') != '/j-webtek/tactevra/issues/new'):
        return None
    templates = parse_qs(parsed.query, keep_blank_values=True).get('template')
    if templates is None:
        return None  # Generic new-issue link, not a template link.
    if len(templates) != 1 or not templates[0]:
        return f'ambiguous or empty issue template: {target}'
    name = templates[0]
    if name == 'BLANK_ISSUE':
        return None  # GitHub's built-in fallback, not a file.
    if not re.fullmatch(r'[A-Za-z0-9_-]+\.(?:md|yml|yaml)', name):
        return f'invalid issue template filename: {target}'
    if not (root / '.github' / 'ISSUE_TEMPLATE' / name).is_file():
        return f'missing issue template: {name}'
    return None


def readiness_dashboard_errors(content: str, root: Path) -> list[str]:
    """Keep the public blocker count and routes aligned with the offline registry."""
    path = root / '.github' / 'release-readiness.json'
    try:
        registry = json.loads(path.read_text(encoding='utf-8'))
        blockers = registry['blockers']
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return [f'invalid release-readiness registry: {exc}']
    if not isinstance(blockers, list):
        return ['invalid release-readiness registry: blockers must be a list']
    open_entries = [entry for entry in blockers
                    if isinstance(entry, dict) and entry.get('status') == 'open']
    errors = []
    match = re.search(r'currently has (\w+) open blocker(?:s)?\.', content)
    words = {
        0: 'zero', 1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five',
        6: 'six', 7: 'seven', 8: 'eight', 9: 'nine', 10: 'ten',
    }
    expected = words.get(len(open_entries), str(len(open_entries)))
    if not match or match.group(1) != expected:
        errors.append(f'expected public open-blocker count: {expected}')
    for entry in open_entries:
        issue = entry.get('issue')
        if not isinstance(issue, str) or issue not in content:
            errors.append(f'missing open readiness blocker route: {issue!r}')
    return errors


def main() -> None:
    errors = []
    for relative in DOCS:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f'Missing maintained document: {relative}')
            continue
        raw_content = path.read_text(encoding='utf-8')
        if 'j-webtek/robot-arm-build' in without_fences(raw_content):
            errors.append(
                f'{relative}: stale canonical repository reference; use j-webtek/tactevra')
        errors.extend(f'{relative}: {error}'
                      for error in public_entry_errors(relative, raw_content, ROOT))
        if relative == 'docs/releases/READINESS.md':
            errors.extend(f'{relative}: {error}' for error in
                          readiness_dashboard_errors(raw_content, ROOT))
        content = without_fences(raw_content)
        for target in re.findall(r'\]\(([^)]+)\)', content):
            target = target.strip().strip('<>')
            parsed = urlsplit(target)
            template_error = issue_template_error(target, ROOT)
            if template_error:
                errors.append(f'{relative}: {template_error}')
            if parsed.scheme or target.startswith('#'):
                continue
            if not (path.parent / unquote(parsed.path)).exists():
                errors.append(f'{relative}: missing local target {target}')
    for asset in ('tactevra-banner.svg', 'tactevra-mark.svg'):
        try:
            root = ET.parse(ROOT / 'assets/brand' / asset).getroot()
            if root.tag != '{http://www.w3.org/2000/svg}svg':
                errors.append(f'{asset}: expected SVG root')
        except (OSError, ET.ParseError) as exc:
            errors.append(f'{asset}: {exc}')
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'PASS: local file links in {len(DOCS)} maintained docs, '
          f'{len(PUBLIC_TITLES)} public titles, required navigation, and two SVG assets')


if __name__ == '__main__':
    main()
