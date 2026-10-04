"""Closed diagnostic action catalog for the first local workbench.

This catalog issues no arm/motion authority. The original-bound camera probe
and bounded settings capture use separate effectful parent paths; stage-6
freshness capture and serial remain held. Browser
input selects a registered action and bounded semantic fields, never a command
line, provider class, device path or authority bit.
"""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
import math
import re
from typing import Any, Mapping, cast


def example_plan_text():
    """Inert catalog default; keep importing the catalog free of motion engines.

    Isolated feedback workers import this catalog through the diagnostic codec.
    The example is validated by the movement planner only when explicitly used.
    """
    import json
    axes = ('x_mm','y_mm','z_mm','pitch_rad','roll_rad','gripper_rad')
    start = dict.fromkeys(axes,0)
    target = dict(start,x_mm=1)
    stop = {'max_read_gap_s':.1,'position_tolerance_mm':.1,
            'angle_tolerance_rad':.01,'max_endpoint_error_mm':.5}
    plan = {'schema':'rocell.characterization_plan.v1','campaign_id':'synthetic-example','frame':'R_ctrl',
        'evidence':{**dict.fromkeys(('source_sha256','configuration_sha256',
            'firmware_review_sha256','geometry_sha256'),'0'*64),
            'usb_identity':'synthetic-not-a-device','tool_payload_id':'synthetic-no-tool'},
        'limits':{'minimum_pose':dict.fromkeys(axes,-10),'maximum_pose':dict.fromkeys(axes,10),
            'max_translation_mm':2,'max_rotation_rad':.1,'min_spd':.01,'max_spd':.1,
            'max_trials':4,'max_duration_s':20},
        'trials':[{'trial_id':name,'command_family':'T104','start':a,'target':b,
                   'spd':.05,'dwell_s':.5,'timeout_s':2,'stop':stop}
                  for name,a,b in [('out',start,target),('back',target,start)]]}
    return json.dumps(plan,separators=(',',':'))


PORTABLE_SETUP_ACTORS = {
    "run_positional_campaign": "operator_id",
    "run_first_motion": "operator_id",
    "record_first_motion_measurements": "operator_id",
    "run_endpoint_trial": "operator_id",
    "record_powered_arm_startup": "operator_id",
    "record_passive_arm_setup": "operator_id",
    "physical_camera_initialize": "operator_id",
    "physical_camera_refresh": "operator_id",
    "physical_camera_prerequisites": "operator_id",
    "physical_camera_discover": "operator_id",
    "physical_camera_reopen": "operator_id",
    "physical_camera_assess_sources": "operator_id",
    "physical_camera_review_sources": "reviewer_id",
    "physical_camera_configuration": "operator_id",
}
PORTABLE_SETUP_OPERATOR_HELP = (
    "Use 1–64 ASCII letters, digits, underscores, hyphens or periods; "
    "start with a letter or digit. Spaces are not allowed."
)


def portable_setup_operator_valid(value: Any) -> bool:
    """Same existing portable-ID rule at preview and original setup execution."""
    return (
        type(value) is str
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value) is not None
    )


class WizardError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class ActionDefinition:
    action_id: str
    label: str
    section: str
    description: str
    worker: str
    timeout_s: int = 60
    fields: tuple[dict[str, Any], ...] = ()
    mode: str = "both"
    hold: str | None = None

    def view(self, *, mode: str, busy: bool) -> dict[str, Any]:
        reasons = []
        if self.hold:
            reasons.append(self.hold)
        if self.mode not in ("both", mode):
            reasons.append(
                f"Available only in {self.mode} mode; restart explicitly in that mode."
            )
        if busy and self.action_id not in ("stop_operation",):
            reasons.append(
                "A diagnostic action is running. Wait for cleanup or explicitly stop it."
            )
        fields = [deepcopy(value) for value in self.fields]
        for field in fields:
            if field["name"] == PORTABLE_SETUP_ACTORS.get(self.action_id):
                field["help"] = PORTABLE_SETUP_OPERATOR_HELP
        return {
            "action_id": self.action_id,
            "label": self.label,
            "section": self.section,
            "description": self.description,
            "enabled": not reasons,
            "blocked_reasons": reasons,
            "fields": fields,
            "timeout_s": self.timeout_s,
        }


def _select(
    name: str, label: str, values: tuple[str, ...], default: str
) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "type": "select",
        "default": default,
        "required": True,
        "options": [{"value": v, "label": v.replace("-", " ")} for v in values],
    }


CAMERA_FAULTS = (
    "none",
    "wrong-camera-identity",
    "wrong-camera-mode",
    "stale-camera-frame",
    "camera-identity-drift",
    "camera-close-failure",
)
ARM_FAULTS = (
    "none",
    "wrong-arm-identity",
    "dirty-arm-buffer",
    "malformed-t1051-response",
    "retry-prohibition",
)
TEXT_FIELD = {
    "name": "text",
    "label": "Non-sensitive test text",
    "type": "textarea",
    "required": True,
    "default": "hello",
    "max_length": 64,
}
DEVICE_FIELD = _select("device", "Target device", ("keyboard", "phone"), "keyboard")
PHYSICAL_HOLD = "Physical activation is blocked: complete reviewed v2 coordinator/qualification, static-primary migration and stage evidence first. No device will be opened."

ENDPOINT_OPERATOR_CHECK_LABELS = {
    'secured_installation':'The arm is secured and stationary now.',
    'full_arm_and_cable_clearance':'The full arm and cables have clearance for this exact trial.',
    'gravity_drop_envelope':'The area where the arm could fall on power loss is clear.',
    'reachable_power_shutdown':'I can reach the supplied-power shutdown; cancellation is not an emergency stop.',
    'operator_present':'I am beside the arm and will remain present throughout this trial.',
    'exact_target_and_speed_approved':'I approve only the displayed target and speed, with no return or retry.',
    'endpoint_only_limitations':'I understand endpoint telemetry does not prove continuous clearance or physical stopping.',
}

ACTIONS = (
    ActionDefinition('use_current_arm_for_observational_test','Use connected arm for observational testing','arm',
        'Reuse this session\'s correlated USB metadata and fixed vendor protocol review. Model and firmware history remain your report, not an installed-binary verification. No device access or movement.',
        'observational_onboarding_parent',timeout_s=30,mode='physical',
        fields=({'name':'operator_id','label':'Your name or operator label','type':'text','required':True,'max_length':64,'default':''},
                {'name':'confirm_model','label':'This is my RoArm-M3 Pro.','type':'checkbox','required':True,'default':False},
                {'name':'firmware_unchanged','label':'Its firmware is unchanged since delivery.','type':'checkbox','required':True,'default':False})),
    ActionDefinition('setup_observational_movement','Prepare observational wrist test','arm',
        'Select host-reviewed arm/protocol records and stage the fixed runtime. No measurements, key creation, device opening or movement.',
        'observational_setup_parent',timeout_s=30,mode='physical',
        fields=(_select('source_id','Reviewed arm and protocol records',(),''),
                _select('direction','Wrist-pitch direction (relative to captured baseline)',('-1','1'),'-1'),
                _select('degrees','Wrist increment in degrees (relative mode only)',('1','5'),'1'),
                _select('absolute_draft','Target mode: relative increment or retained absolute draft',('relative',),'relative'))),
    ActionDefinition('run_observational_movement','Run one small observational wrist test','arm',
        'May open the arm and move wrist pitch by the displayed 1 or 5 degrees from the captured baseline at spd 20, acc 1. No return or retry. Serial opening can cause startup movement; cancellation is not an emergency stop.',
        'observational_run_parent',timeout_s=35,mode='physical',
        fields=({'name':'operator_id','label':'Your name or operator label','type':'text','required':True,'max_length':64,'default':''},)
        + tuple({'name':name,'label':label,'type':'checkbox','required':True,'default':False} for name,label in (
            ('secured_and_clear','The arm is secured; the full arm and cable movement area is clear.'),
            ('operator_present_and_shutdown_reachable','I am present and can reach the power shutdown.'),
            ('starting_pose_visually_consistent','The current pose has clear space for the displayed small wrist movement.'),
            ('bounded_policy_accepted','I accept only the displayed wrist increment, with no return or retry.')))),
    ActionDefinition('record_observational_movement','Record what the arm did','arm',
        'Record your observation of a retained observational trial. No measurements, photo, device access or new movement required.',
        'observational_operator_parent',timeout_s=30,mode='physical',
        fields=(_select('trial','Retained observational trial',(),''),
                {'name':'observer_id','label':'Your name or operator label','type':'text','required':True,'max_length':64,'default':''},
                _select('outcome','What happened?',('UNKNOWN','EXPECTED_MOVEMENT','NO_MOVEMENT','WRONG_MOVEMENT'),'UNKNOWN'),
                {'name':'covered_trial','label':'I watched the entire movement test.','type':'checkbox','required':False,'default':False},
                {'name':'detail','label':'Notes (optional): noise, vibration, cables or anything unexpected','type':'textarea','required':False,'max_length':1024,'default':''})),
    ActionDefinition('run_first_motion','Run one reviewed wrist commissioning test','arm',
        'May open the arm controller and send one fixed wrist command after admission. No return or retry. Cancellation is not a physical emergency stop.',
        'first_motion_run_parent',timeout_s=35,mode='physical',
        fields=({'name':'selection_sha256','label':'Displayed commissioning selection SHA-256','type':'text','required':True,'max_length':64,'default':''},
                {'name':'operator_id','label':'Operator identity','type':'text','required':True,'max_length':64,'default':''})
                + tuple({'name':name,'label':label,'type':'checkbox','required':True,'default':False} for name,label in (
                    ('secured_installation','The arm installation is secured.'),
                    ('full_arm_and_cable_clearance','The full arm and cable movement area is clear.'),
                    ('gravity_drop_envelope','The possible gravity-drop area is clear.'),
                    ('reachable_power_shutdown','I can reach the physical power shutdown.'),
                    ('operator_present','I am beside the arm and will remain present.'),
                    ('exact_wrist_target_and_speed_approved','I approve only the displayed fixed wrist target and speed, without return or retry.'),
                    ('unknown_freshness_experiment_acknowledged','I understand that telemetry freshness remains unqualified.')))),
    ActionDefinition('create_first_motion_draft','Create commissioning draft from retained records','arm',
        'Select this session\'s measurement and supporting originals. Generate an untimed review draft; no approval, device access or movement.',
        'first_motion_draft_parent',timeout_s=30,mode='physical',
        fields=(_select('measurement_operation_id','Successful measurement record',(),''),
                _select('support_record_id','Retained supporting record set',(),''))),
    ActionDefinition('review_first_motion_qualification','Record functional-response qualification review','arm',
        'Review one retained assessment. Acceptance cannot override holds and grants no permission for another move or calibrated accuracy claim.',
        'first_motion_qualification_review_parent',timeout_s=30,mode='physical',
        fields=(_select('assessment_operation_id','Retained assessment',(),''),
                {'name':'reviewer_id','label':'Reviewer identity (self-reported)','type':'text','required':True,'max_length':64,'default':''},
                _select('decision','Explicit decision',('UNKNOWN','REJECT','ACCEPT_FUNCTIONAL_RESPONSE'),'UNKNOWN'),
                {'name':'rationale','label':'Review evidence, limitations and rationale','type':'textarea','required':True,'max_length':1024,'default':''}) + tuple(
                    {'name':name,'label':label,'type':'checkbox','required':False,'default':False} for name,label in (
                        ('observer_identity_reviewed','I reviewed the observer identity.'),
                        ('method_compliance_reviewed','I reviewed compliance with the planned observation method.'),
                        ('observation_timing_reviewed','I reviewed observation timing and coverage of this exact trial.'),
                        ('discrepancies_resolved','I reviewed and resolved discrepancies before acceptance.')))),
    ActionDefinition('assess_first_motion_qualification','Assess commissioning evidence for review','arm',
        'Reconstruct saved telemetry, match the owned process receipt and correlate one retained observation. This is not qualification or permission for another move.',
        'first_motion_qualification_parent',timeout_s=30,mode='physical',
        fields=(_select('observation_operation_id','Successful retained observation',(),''),)),
    ActionDefinition('record_first_motion_observation','Record observation of completed commissioning trial','arm',
        'Retain what you observed against this session\'s exact result. Reporting expected movement is not physical qualification or permission for another trial.',
        'first_motion_observation_parent',timeout_s=30,mode='physical',
        fields=(_select('trial','Retained trial result',(),''),
                {'name':'observer_id','label':'Observer identity (self-reported)','type':'text','required':True,'max_length':64,'default':''},
                _select('method','Observation method',('LIVE_VISUAL','VIDEO_REVIEW'),'LIVE_VISUAL'),
                _select('outcome','Observed movement',('UNKNOWN','EXPECTED_MOVEMENT','NO_MOVEMENT','WRONG_MOVEMENT'),'UNKNOWN'),
                _select('coverage','Observed portion',('UNKNOWN','ENTIRE_TRIAL','PARTIAL'),'UNKNOWN'),
                {'name':'detail','label':'What happened, including discrepancies','type':'textarea','required':True,'max_length':1024,'default':''},
                {'name':'limitations','label':'Observation and timing limitations','type':'textarea','required':True,'max_length':1024,'default':''})),
    ActionDefinition('attach_retained_first_motion','Attach reviewed commissioning records (no movement)','arm',
        'Attach one saved draft and five explicit engineering approvals. Reads the existing private review key; does not create a key, open hardware or run the arm.',
        'first_motion_attachment_parent',timeout_s=30,mode='physical',
        fields=(_select('draft_operation_id','Retained commissioning draft',(),''),) + tuple(
            _select(check,check.replace('_',' ').capitalize(),(),'') for check in (
                'received_unit_and_usb_association','installed_unit_command_compatibility',
                'independent_starting_geometry_review','independent_observation_method_ready','owned_connection_and_cleanup_ready'))),
    ActionDefinition('review_retained_first_motion_draft','Review a retained commissioning draft','arm',
        'Select a successful draft from this session and record one explicit engineering decision. No copied JSON, automatic approval or hardware access.',
        'first_motion_retained_review_parent',timeout_s=30,mode='physical',
        fields=(_select('draft_operation_id','Retained commissioning draft',(),''),
                {'name':'reviewer_id','label':'Reviewer identity (self-reported)','type':'text','required':True,'max_length':64,'default':''},
                _select('check','Engineering check',('received_unit_and_usb_association','installed_unit_command_compatibility',
                    'independent_starting_geometry_review','independent_observation_method_ready','owned_connection_and_cleanup_ready'),'received_unit_and_usb_association'),
                _select('decision','Explicit decision',('UNKNOWN','DENIED','APPROVED'),'UNKNOWN'),
                {'name':'detail','label':'Evidence and rationale; state limitations','type':'textarea','required':True,'max_length':1024,'default':''})),
    ActionDefinition('record_first_motion_engineering_review','Record commissioning engineering decision from JSON (advanced)','arm',
        'Retain an explicit decision about one wrist-test selection. Unknown and denied decisions remain in logs. Recording neither verifies the reviewer nor authorizes motion.',
        'first_motion_engineering_intake_parent',timeout_s=30,mode='physical',
        fields=({'name':'draft_json','label':'Exact commissioning draft JSON','type':'textarea','required':True,'max_length':16384,'default':''},
                {'name':'reviewer_id','label':'Reviewer identity (self-reported)','type':'text','required':True,'max_length':64,'default':''},
                _select('check','Engineering check',('received_unit_and_usb_association','installed_unit_command_compatibility',
                    'independent_starting_geometry_review','independent_observation_method_ready','owned_connection_and_cleanup_ready'),'received_unit_and_usb_association'),
                _select('decision','Explicit decision',('UNKNOWN','DENIED','APPROVED'),'UNKNOWN'),
                {'name':'detail','label':'Evidence and rationale; state limitations','type':'textarea','required':True,'max_length':1024,'default':''})),
    ActionDefinition('record_endpoint_engineering_review','Record endpoint engineering decision (no hardware)','arm',
        'Retain one explicit review of an exact draft. Recording is not independent verification or motion permission. Unknown and denied decisions remain in logs.',
        'endpoint_engineering_intake_parent',timeout_s=30,mode='physical',
        fields=({'name':'draft_json','label':'Exact endpoint draft JSON','type':'textarea','required':True,'max_length':16384,'default':''},
                {'name':'reviewer_id','label':'Reviewer identity (self-reported)','type':'text','required':True,'max_length':64,'default':''},
                _select('check','Engineering check',('received_unit_and_usb_association','installed_firmware_compatibility',
                    'controller_frame_and_baseline_qualified','noncontact_route_review','owned_connection_and_cleanup_ready'),'received_unit_and_usb_association'),
                _select('decision','Explicit decision',('UNKNOWN','DENIED','APPROVED'),'UNKNOWN'),
                {'name':'detail','label':'Evidence and rationale; state limitations','type':'textarea','required':True,'max_length':1024,'default':''})),
    ActionDefinition('review_endpoint_campaign','Review saved endpoint campaign (no hardware)','arm',
        'Read explicitly selected native endpoint exports from the assigned export folder. Rebuild comparisons from originals; failed and missing trials remain visible. No motion or automatic settings changes.',
        'endpoint_campaign_review_parent',timeout_s=60,
        fields=({'name':'plan_json','label':'Exact saved campaign JSON','type':'textarea',
                 'required':True,'max_length':16384,'default':''},
                {'name':'attempt_ids','label':'Saved operation IDs (one per line)','type':'textarea',
                 'required':True,'max_length':6000,'default':''})),
    ActionDefinition('assess_saved_wrist_correction','Assess saved directional-error trials (no hardware)','arm',
        'Reconstruct two to eight selected absolute wrist exports and assess a bounded correction hypothesis. This does not authorize motion or verify physical provenance.',
        'saved_wrist_correction_parent',timeout_s=60,
        fields=({'name':'attempt_ids','label':'Saved absolute operation IDs (one per line)','type':'textarea',
                 'required':True,'max_length':400,'default':''},)),
    ActionDefinition('bind_saved_wrist_correction','Match correction assessment to reviewed arm (no hardware)','arm',
        'Recheck a retained correction hypothesis and match all trial identities to a reviewed controller. This does not establish current pose or authorize motion.',
        'bind_saved_wrist_correction_parent',timeout_s=60,mode='physical',
        fields=(_select('assessment_operation_id','Saved correction assessment',(),''),
                _select('source_id','Reviewed arm source',(),''))),
    ActionDefinition('stage_wrist_correction','Prepare correction runtime (no hardware)','arm',
        'Revalidate a matched assessment and retain a pinned execution package. Preparation does not open the arm, sign a movement review, or authorize execution.',
        'stage_wrist_correction_parent',timeout_s=60,mode='physical',
        fields=(_select('binding_operation_id','Matched correction assessment',(),''),)),
    ActionDefinition('run_wifi_roll_adjacent_lookup_trial','Validate frozen 1.50-degree lookup (Wi-Fi)','arm',
        'LIVE held-out descending lookup: desired 1.50, command 1.25 degrees. Existing limits, speed 20/acc 1; no retry or global enablement.',
        'wifi_roll_adjacent_lookup_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_wifi_roll_adjacent_low_trial','Probe 1.25-degree command for 1.50-degree target (Wi-Fi)','arm',
        'LIVE descending characterization: desired 1.50, command 1.25 degrees. Existing limits, speed 20/acc 1; no retry or model update.',
        'wifi_roll_adjacent_low_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_wifi_roll_adjacent_high_trial','Probe 1.35-degree command for 1.50-degree target (Wi-Fi)','arm',
        'LIVE descending characterization: desired 1.50, command 1.35 degrees. Existing limits, speed 20/acc 1; no retry or model update.',
        'wifi_roll_adjacent_high_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_wifi_roll_sweep_low_trial','Sweep descending command 0.85 degrees (Wi-Fi)','arm',
        'LIVE characterization: desired 1.25, command 0.85. Existing delta limits, speed 20/acc 1; no retry or fitting.',
        'wifi_roll_sweep_low_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_wifi_roll_sweep_center_trial','Sweep descending command 0.95 degrees (Wi-Fi)','arm',
        'LIVE characterization: desired 1.25, command 0.95. Not held-out lookup validation; no retry or fitting.',
        'wifi_roll_sweep_center_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_wifi_roll_sweep_high_trial','Sweep descending command 1.05 degrees (Wi-Fi)','arm',
        'LIVE characterization: desired 1.25, command 1.05. Existing delta limits, speed 20/acc 1; no retry or fitting.',
        'wifi_roll_sweep_high_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_wifi_roll_adjacent_trial','Characterize descending roll 1.50 degrees (Wi-Fi)','arm',
        'LIVE uncorrected characterization: desired and commanded roll 1.50 degrees. Existing delta limits, speed 20/acc 1; no retry or model update.',
        'wifi_roll_adjacent_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_wifi_roll_lookup_trial','Validate frozen descending lookup (Wi-Fi)','arm',
        'LIVE held-out lookup validation: desired 1.25 degrees, command 0.95 degrees. Existing limits, speed 20/acc 1; no retry or model update.',
        'wifi_roll_lookup_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_wifi_roll_probe_low_trial','Characterize descending roll command 0.95 degrees (Wi-Fi)','arm',
        'LIVE local response probe: desired 1.25 degrees, command 0.95 degrees. Existing delta limits, speed 20/acc 1; no retry or model update.',
        'wifi_roll_probe_low_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_wifi_roll_probe_high_trial','Characterize descending roll command 1.15 degrees (Wi-Fi)','arm',
        'LIVE local response probe: desired 1.25 degrees, command 1.15 degrees. Existing delta limits, speed 20/acc 1; no retry or model update.',
        'wifi_roll_probe_high_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_wifi_roll_corrected_up_trial','Test frozen roll correction from below (Wi-Fi)','arm',
        'LIVE held-out trial: desired 1.25 degrees, command 1.3134765703 degrees. Existing step limits, speed 20/acc 1; no retry.',
        'wifi_roll_corrected_up_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_wifi_roll_corrected_down_trial','Test frozen roll correction from above (Wi-Fi)','arm',
        'LIVE held-out trial: desired 1.25 degrees, command 1.0498046875 degrees. Existing step limits, speed 20/acc 1; no retry.',
        'wifi_roll_corrected_down_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_wifi_roll_zero_trial','Position roll at 0 degrees from above (Wi-Fi)','arm',
        'LIVE single positioning leg. Fresh descending delta >0.5 and <=1.5 degrees, speed 20/acc 1; no retry or automatic next movement.',
        'wifi_roll_zero_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_wifi_roll_center_up_trial','Approach roll 1.25 degrees from below (Wi-Fi)','arm',
        'LIVE same-target comparison leg. Fresh ascending delta >0.5 and <=1.5 degrees; speed 20/acc 1; no retry or automatic next movement.',
        'wifi_roll_center_up_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_wifi_roll_center_down_trial','Approach roll 1.25 degrees from above (Wi-Fi)','arm',
        'LIVE same-target comparison leg. Fresh descending delta >0.5 and <=1.5 degrees; speed 20/acc 1; no retry or automatic next movement.',
        'wifi_roll_center_down_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_wifi_roll_low_trial','Move roll to 1 degree from above (Wi-Fi)','arm',
        'LIVE fixed-target trial: descending to 1 degree only when fresh delta is >0.5 and <=1.5 degrees. Speed 20/acc 1; no retry or automatic return.',
        'wifi_roll_low_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_wifi_roll_high_trial','Move roll to 2.5 degrees from below (Wi-Fi)','arm',
        'LIVE fixed-target trial: ascending to 2.5 degrees only when fresh delta is >0.5 and <=1.5 degrees. Speed 20/acc 1; no retry or automatic return.',
        'wifi_roll_high_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_wifi_roll_negative_trial','Move roll -1 degree and verify (Wi-Fi)','arm',
        'LIVE movement: one fresh-baseline roll -1 degree command, target limited to +/-3 degrees, speed 20/acceleration 1. Ten-second completion budget; no retry or automatic return. Requires a secured powered arm and clear workspace.',
        'wifi_roll_negative_trial_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_wifi_roll_trial','Move roll +1 degree and verify (Wi-Fi)','arm',
        'LIVE movement: one fresh-baseline roll +1 degree command, target limited to +/-3 degrees, speed 20/acceleration 1. Ten-second completion budget, no return or retry. Requires a secured powered arm and clear workspace.',
        'wifi_roll_trial_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('observe_arm_wifi_bounded','Test Wi-Fi absolute deadlines (no movement)','arm',
        '35-second feedback-only test with 150 ms cooldown and an 800 ms shared HTTP I/O deadline. No commands other than T105; no retry.',
        'wifi_absolute_deadline_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_micro_commissioning','LIVE: predecessor and optional single micro-command','arm',
        'At most two commands: descending 0.95 degrees, then eligible 0.90 degrees. No repositioning, retry or return. Two passive holds and automatic diagnostic exports.',
        'micro_commissioning_parent',timeout_s=180,mode='physical',fields=(
            {'name':'exclusive_controller_declared','label':'No other web UI, SDK, task or computer will command the arm during this test.','type':'checkbox','required':True,'default':False},)),
    ActionDefinition('simulate_micro_correction','Test micro-correction policies (simulation only)','arm',
        'Seventeen synthetic policy and command-strategy checks. No network, USB, movement or live admission. Exportable results.',
        'micro_correction_simulation_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('run_held_pair','Run host-bound elbow forward/return test','arm',
        'LIVE: one bounded forward command and an evidence-gated return. Requires separate trusted host admission. No retry; cancellation prevents the next operation, not motion already sent.',
        'held_pair_parent',timeout_s=180,mode='physical',fields=(
            {'name':'acknowledge','label':'Run the exact host-bound elbow pair shown in the preview.','type':'checkbox','required':True,'default':False},)),
    ActionDefinition('review_pose_policy','Review repositioned pose against installed settings (offline)','arm',
        'Replay saved pose and installation evidence. Identify outdated joint windows; encoder limits are not physical clearance. No connection, startup, movement or settings changes. Export logs retains the comparison.',
        'pose_policy_review',timeout_s=30,fields=tuple(
            {'name':name,'label':label,'type':'text','required':True,'max_length':90,'default':''}
            for name,label in (
                ('pose_export','Three-snapshot pose export folder (wizard-...)'),
                ('stage_export','Installed settings staging export folder (wizard-...)'),
                ('installation_export','Settings installation export folder (wizard-...)')))),
    ActionDefinition('review_observed_pair','Review saved forward/return endpoints (offline)','arm',
        'Replay saved pair evidence and source authorization/delivery links. Servo counts only; no connection, movement or retry.',
        'observed_pair_review_parent',timeout_s=60,fields=(
            {'name':'export_id','label':'Observed return export folder (wizard-...)','type':'text','required':True,'max_length':90,'default':''},)),
    ActionDefinition('review_observed_hold','Review saved controller hold observation (offline)','arm',
        'Replay a saved HTTP observation and command-linked servo counts. No hardware access or retry; not measured stylus accuracy.',
        'observed_hold_review_parent',timeout_s=30,fields=(
            {'name':'export_id','label':'Observed hold export folder (wizard-...)','type':'text','required':True,'max_length':90,'default':''},)),
    ActionDefinition('review_collected_hold','Review saved hold simulation and endpoints (offline)','arm',
        'Replay the prepared attempt, raw collection and count-level endpoint evidence. Simulation only; no hardware access, retry or qualification.',
        'collected_hold_review_parent',timeout_s=30,fields=(
            {'name':'export_id','label':'Collected hold export folder (wizard-...)','type':'text','required':True,'max_length':90,'default':''},)),
    ActionDefinition('review_started_servo_run','Review saved command delivery and telemetry (offline)','arm',
        'Verify the consumed start claim, delivery record and linked endpoint assessment. Never resend or connect to hardware.',
        'started_servo_review_parent',timeout_s=30,fields=(
            {'name':'export_id','label':'Started-run export folder (wizard-...)','type':'text','required':True,'max_length':90,'default':''},)),
    ActionDefinition('review_startup_servo_run','Review saved startup command and endpoint (offline)','arm',
        'Replay startup scans, control-state checks, command evidence and endpoint assessment. Incomplete evidence stays inconclusive. No device access or retry.',
        'startup_servo_review_parent',timeout_s=30,fields=(
            {'name':'export_id','label':'Startup-run export folder (wizard-...)','type':'text','required':True,'max_length':90,'default':''},)),
    ActionDefinition('review_started_startup_run','Review startup delivery and endpoint together (offline)','arm',
        'Verify the consumed startup attempt and linked endpoint evidence without reconnecting or resending.',
        'started_startup_review_parent',timeout_s=30,fields=(
            {'name':'export_id','label':'Linked startup export folder (wizard-...)','type':'text','required':True,'max_length':90,'default':''},)),
    ActionDefinition('review_planned_servo_run','Review saved planned servo run (offline)','arm',
        'Verify the frozen plan, retained controller records and combined assessment. No hardware access or movement.',
        'planned_servo_review_parent',timeout_s=30,fields=(
            {'name':'export_id','label':'Planned-run export folder (wizard-...)','type':'text','required':True,'max_length':90,'default':''},)),
    ActionDefinition('simulate_servo_diagnostics','Rehearse servo diagnostics (simulation only)','arm',
        'Assess a synthetic command/readback/acquisition trace and automatically export and replay it. No device access or movement qualification.',
        'servo_diagnostic_simulation_parent',timeout_s=30,mode='physical',fields=(
            _select('scenario','Synthetic diagnostic case',('arrival','bus_failure','wrong_target','failed_read','no_readback','stationary','delayed_arrival','reboot','stale_sequence','paired_arrival','paired_negative_position','paired_stale_read','paired_failed_read'),'arrival'),)),
    ActionDefinition('simulate_discrete_transaction','Test discrete transaction logic (simulation only)','arm',
        'Seven deterministic in-memory command/feedback scenarios. No network, USB or movement. Results can be exported.',
        'discrete_transaction_simulation_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('observe_arm_wifi_feedback_intermediate','Observe Wi-Fi with 150 ms cooldown (no movement)','arm',
        'Separate 35-second diagnostic with 150 ms quiet after each response, at most 234 requests. First-fault stop; no movement or retry.',
        'arm_wifi_observation_intermediate_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('observe_arm_wifi_feedback_spaced','Observe Wi-Fi with connection cooldown (no movement)','arm',
        '35-second diagnostic with 500 ms quiet after each response, at most 70 requests. First-fault stop, original retention, no movement or retry.',
        'arm_wifi_observation_spaced_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('observe_arm_wifi_feedback_fast','Observe Wi-Fi feedback at up to 10 Hz (no movement)','arm',
        'Separate 35-second, at-most-400-request feedback observation. Same identity, retention and transport lock checks; first-fault stop, no movement or retry.',
        'arm_wifi_observation_fast_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('observe_arm_wifi_feedback','Observe Wi-Fi feedback for 35 seconds (no movement)','arm',
        'Finite feedback-only observation with original numeric responses, identity checks and participating-transport lock. No movement or retries.',
        'arm_wifi_observation_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('sample_arm_wifi_feedback','Measure Wi-Fi feedback timing (no movement)','arm',
        'Up to eight sequential feedback-only requests to the pinned arm. Stop on the first fault; no movement, retry or configuration changes.',
        'arm_wifi_sampling_parent',timeout_s=60,mode='physical',fields=()),
    ActionDefinition('read_arm_wifi_feedback','Read arm positions over Wi-Fi (no movement)','arm',
        'One feedback-only HTTP request to the commissioned arm at 192.168.0.225. Checks the expected local MAC; no retry, movement or USB access.',
        'arm_wifi_feedback_parent',timeout_s=20,mode='physical',fields=()),
    ActionDefinition('run_positional_campaign','Run attended joint experiment','arm',
        'Execute only the host-staged command(s), verifying intended endpoints. No retry after a fault. Software cancellation is not a physical stop.',
        'positional_campaign_run_parent',timeout_s=40,mode='physical',
        fields=({'name':'operator_id','label':'Operator label','type':'text','required':True,'max_length':64,'default':''},)
        + tuple({'name':name,'label':label,'type':'checkbox','required':True,'default':False} for name,label in (
            ('secured_and_clear','The arm is secured and the entire accepted movement area is clear.'),
            ('operator_present_and_shutdown_reachable','I am present and power shutdown is reachable.'),
            ('starting_pose_visually_consistent','The current pose is consistent with this preview.'),
            ('enumerated_route_reviewed','I reviewed every displayed intended endpoint and transmitted command.'),
            ('accepted_goal_completion_risk_reviewed','No contact or added payload; an accepted goal may finish after cancellation.')))),
    ActionDefinition('run_wrist_correction','Run one reviewed wrist correction experiment','arm',
        'May open the selected arm and send one bounded experimental wrist target at spd 20, acc 1. Endpoint verification uses the nominal target. No return or retry; cancellation is not an emergency stop.',
        'wrist_correction_run_parent',timeout_s=35,mode='physical',
        fields=({'name':'operator_id','label':'Your name or operator label','type':'text','required':True,'max_length':64,'default':''},)
        + tuple({'name':name,'label':label,'type':'checkbox','required':True,'default':False} for name,label in (
            ('secured_and_clear','The arm is secured and the arm/cable movement area is clear.'),
            ('operator_present_and_shutdown_reachable','I am present and can reach the power shutdown.'),
            ('starting_pose_visually_consistent','The current pose has clear space for the entire displayed joint experiment, including the whole arm sweep.'),
            ('bounded_policy_accepted','I accept the displayed experimental target with no return or retry.')))),
    ActionDefinition('run_endpoint_trial','Run one reviewed noncontact endpoint trial','arm',
        'Execute only the host-bound trial through fresh review, baseline, one command, observation and cleanup. No return, retry or contact. Cancellation is not a physical emergency stop.',
        'endpoint_trial_parent',timeout_s=35,mode='physical',
        fields=({'name':'draft_sha256','label':'Exact displayed draft SHA-256','type':'text',
                 'required':True,'max_length':64,'default':''},
                {'name':'acknowledge','label':'I have reviewed this exact trial; independent current safety reviews are still required.',
                 'type':'checkbox','required':True,'default':False},
                {'name':'operator_id','label':'Operator identity','type':'text','required':True,'max_length':64,'default':''})
               + tuple({'name':name,'label':label,'type':'checkbox','required':True,'default':False}
                       for name,label in ENDPOINT_OPERATOR_CHECK_LABELS.items())),
    ActionDefinition('movement_endpoint_review','Inspect exact endpoint request (no movement)','arm',
        'Show start/target coordinates, speed semantics and required reviews from retained request JSON. Inspection is not approval or execution.',
        'endpoint_request_review',timeout_s=30,
        fields=({'name':'request_json','label':'Retained endpoint request JSON (review only)',
                 'type':'textarea','required':True,'max_length':12000,'default':''},)),
    ActionDefinition('review_cartesian_export','Review saved Cartesian/elbow trial (no movement)','arm',
        'Verify a workspace export and compare commanded versus reported joint response. No connection, replay, compensation or motion approval.',
        'cartesian_export_review',timeout_s=30,
        fields=({'name':'export_id','label':'Workspace export folder name (wizard-...)',
                 'type':'text','required':True,'max_length':90,'default':''},)),
    ActionDefinition('review_product_ghost_case','Review full-size keyboard simulation export','tasks',
        'Verify a saved product case and its individual endpoint traces. No connection, movement or replay; synthetic evidence only.',
        'product_ghost_case_review',timeout_s=60,
        fields=({'name':'export_id','label':'Product case export folder (not suite index)',
                 'type':'text','required':True,'max_length':90,'default':''},)),
    ActionDefinition('rehearse_ghost_endpoints','Test ghost sequence endpoints (simulation only)','tasks',
        'Exercise sequential endpoint verification and fault-stop behavior with synthetic transport. No camera or arm connection.',
        'ghost_endpoints',timeout_s=60,
        fields=({'name':'text','label':'Ghost sequence (a/b/c)','type':'text','required':True,'max_length':8,'default':'aba'},
                _select('fault','Injected fault',('NONE','BASELINE_MISMATCH','SHORT_WRITE','UNCHANGED','CANCEL_AFTER_WRITE','CLEANUP_PENDING','DELAYED_ARRIVAL','MISSING_FEEDBACK','POSITION_BIAS'),'NONE'),
                {'name':'fault_trial','label':'Fault at nonzero-motion trial (1-based)','type':'number','required':True,'min':1,'max':32,'step':1,'default':2})),
    ActionDefinition('rehearse_ghost_keyboard','Preview ghost keyboard (camera-free, no movement)','tasks',
        'Compile virtual A/B/C keys into nominal free-space travel, hover, downstroke and retract paths. No camera, arm connection or physical accuracy claim.',
        'ghost_keyboard',timeout_s=30,
        fields=({'name':'text','label':'Ghost sequence (1–8 lowercase a/b/c)','type':'text',
                 'required':True,'max_length':8,'default':'aba'},)),
    ActionDefinition('review_tap_capture','Review phone tap-test capture (no movement)','tasks',
        'Review a supplied benign phone target transcript. CSS pixels are not board coordinates; no robot attribution or contact approval.',
        'tap_capture_review',timeout_s=30,
        fields=({'name':'capture_json','label':'Phone tap capture JSON','type':'textarea',
                 'required':True,'max_length':12000,'default':''},)),
    ActionDefinition('review_input_capture','Review keyboard test-pad capture (no movement)','tasks',
        'Check observed key-down, text and release events against harmless expected text. Browser events do not identify a robot or approve contact.',
        'input_capture_review',timeout_s=30,
        fields=({'name':'capture_json','label':'Test-pad capture JSON','type':'textarea',
                 'required':True,'max_length':12000,'default':''},)),
    ActionDefinition('bench_review_key_setup','Set up private bench review key','arm',
        'Check or explicitly create the Windows-protected local review key. No arm connection, review approval or movement.',
        'bench_review_key_setup',timeout_s=30,mode='physical',
        fields=(_select('operation','Private key operation',('CHECK','PROVISION'),'CHECK'),
                {'name':'acknowledge','label':'This manages only the local review key; it does not approve movement.',
                 'type':'checkbox','required':True,'default':False})),
    ActionDefinition('record_first_motion_measurements','Record independent wrist measurements','arm',
        'Record actual noncontact measurements, including uncertainty. Wrist angle is relative to forearm, not world horizontal. Do not touch or reposition powered joints. Recording is not approval or a serial connection.',
        'first_motion_measurements_parent',timeout_s=30,mode='physical',
        fields=({'name':'operator_id','label':'Measurement observer','type':'text','required':True,'max_length':64,'default':''},
                {'name':'unit_serial','label':'Reported arm USB unit serial','type':'text','required':True,'max_length':32,'default':''},
                _select('method','Independent noncontact method',('NONCONTACT_ANGLE_REFERENCE','CALIBRATED_SIDE_VIEW'),'NONCONTACT_ANGLE_REFERENCE'),
                {'name':'angle_deg','label':'Wrist pitch relative to forearm (degrees)','type':'number','required':True,'min':-180,'max':180,'step':.1,'default':0},
                {'name':'angle_uncertainty_deg','label':'Angle uncertainty (+/- degrees)','type':'number','required':True,'min':.1,'max':30,'step':.1,'default':1},
                {'name':'distal_radius_mm','label':'Wrist axis to furthest distal rigid part (mm)','type':'number','required':True,'min':1,'max':1000,'step':1,'default':0},
                {'name':'radius_uncertainty_mm','label':'Additional radius uncertainty (mm)','type':'number','required':True,'min':0,'max':100,'step':1,'default':1},
                {'name':'observation_notes','label':'Reference, method, measurement time and uncertainty basis','type':'textarea','required':True,'max_length':1024,'default':''},
                {'name':'acknowledge_measured','label':'These are actual independent measurements, not telemetry, a simulation or assumed defaults','type':'checkbox','required':True,'default':False})),
    ActionDefinition('first_motion_review', 'Review first-motion request (no hardware)', 'arm',
        'Inspect the fixed wrist test and its independent-measurement references. Does not approve, connect or execute.',
        'first_motion_review',timeout_s=30,
        fields=({'name':'request_json','label':'Retained commissioning request JSON',
                 'type':'textarea','required':True,'max_length':12000,'default':''},)),
    ActionDefinition('first_motion_rehearse', 'Rehearse first-motion commissioning (no hardware)', 'arm',
        'Inspect the fixed wrist-only proposal and test synthetic telemetry/physical-observation agreement. No device access or live approval. Export logs retains the result.',
        'first_motion_rehearsal', timeout_s=30,
        fields=(_select('scenario','Synthetic commissioning outcome',
            ('NOMINAL','UNCHANGED','TELEMETRY_ONLY','PHYSICAL_ONLY','WRONG_DIRECTION',
             'SHORT_WRITE','CLEANUP_UNCERTAIN','CANCELLED','OTHER_JOINT_MOVED'),'NOMINAL'),)),
    ActionDefinition('movement_endpoint_rehearse', 'Rehearse one endpoint trial (no hardware)', 'arm',
        'Run baseline, one simulated command, endpoint observation and cleanup. Synthetic reviews only; no serial access. Export logs retains the diagnostic result.',
        'movement_endpoint_rehearsal', timeout_s=30,
        fields=({'name':'plan_json','label':'Synthetic campaign JSON', 'type':'textarea',
                 'required':True,'max_length':6000,'default':example_plan_text()},
                {'name':'trial_id','label':'One trial ID (no automatic return)', 'type':'text',
                 'required':True,'max_length':80,'default':'out'},
                _select('fault','Synthetic endpoint fault',
                    ('NONE','BASELINE_MISMATCH','SHORT_WRITE','UNCHANGED','CANCEL_AFTER_WRITE','CLEANUP_PENDING','DELAYED_ARRIVAL','MISSING_FEEDBACK','POSITION_BIAS'),'NONE'))),
    ActionDefinition('movement_saved_capture_review', 'Review saved arm telemetry (no hardware)', 'arm',
        'Verify a saved workspace export and reanalyze every retained complete line. Historical data does not establish current connection or movement readiness.',
        'movement_saved_capture', timeout_s=30,
        fields=({'name':'export_name','label':'Saved folder name under software/runs/wizard-exports',
                 'type':'text','required':True,'max_length':80,
                 'default':'wizard-20260912T232404247125Z-19c8b63e3aa54dcb9ff472dc0d9c23d1'},)),
    ActionDefinition('positional_campaign_boundary_tests', 'Test owned movement pipeline (no hardware)', 'arm',
        'Run the fixed synthetic campaign integration suite: authenticated context, per-leg admission, bounded collection, cancellation, cleanup, reconstruction and proposed servo-freshness fault tests. Proposed telemetry is not installed firmware support. No device opens or physical release.',
        # The closed suite includes real-clock, fake-device rehearsals
        # and isolated package checks (~100 s on the development host). This
        # diagnostic-only budget does not alter any native motion deadline.
        'positional_boundary_tests',timeout_s=180),
    ActionDefinition('positional_campaign_rehearse', 'Rehearse automatic wrist testing (no hardware)', 'arm',
        'Run a finite command/verify sequence against synthetic telemetry. A failed endpoint prevents later simulated commands. No native or unattended motion.',
        'positional_campaign_rehearsal', timeout_s=30,
        fields=(_select('pattern','Synthetic absolute-target pattern',('OUT_AND_BACK','OPPOSITE_APPROACH'),'OUT_AND_BACK'),
                _select('leg_count','Maximum enumerated legs',('2','4','8'),'2'),
                _select('fault_leg','Inject fault at leg',('1','2','3','4','5','6','7','8'),'1'),
                _select('fault','Synthetic fault',('NONE','DIRECTIONAL_OFFSET','NO_RESPONSE','OSCILLATION','DEPARTURE',
                    'OTHER_JOINT','OVERSHOOT','MALFORMED','FEEDBACK_GAP','BATCHED_TIME','BASELINE_DRIFT',
                    'CONTEXT_CHANGED','WRITE_UNCERTAIN','CANCELLED','PERSISTENCE_FAILED','EXPIRED',
                    'REVERSED_DIRECTION','DELAYED_RESPONSE','TIMESTAMP_REGRESSION','MISSING_JOINT',
                    'CPU_STALL','NO_SAMPLES'),'NONE'))),
    ActionDefinition('wrist_correction_rehearse', 'Rehearse directional correction (no hardware)', 'arm',
        'Simulation only: rebuild repeated synthetic trials and check nominal versus adjusted motor targets. Test bias changes, overshoot and invalid starting context. Does not connect to or calibrate the arm. Export logs retains results.',
        'wrist_correction_rehearsal',timeout_s=30,
        fields=(_select('scenario','Synthetic correction scenario',
            ('CONSTANT_BIAS','BIAS_DISAPPEARS','OVERSHOOT','WRONG_APPROACH','STALE_BASELINE'),'CONSTANT_BIAS'),)),
    *(
        ActionDefinition(action_id, label, "arm",
            "Simulation only: validate an explicit finite plan. The default is synthetic, not the connected arm's pose. No device opens or movement permission. Export logs retains the plan and results.",
            "movement_campaign", timeout_s=30,
            fields=({"name":"plan_json","label":"Synthetic campaign JSON (not live commands)",
                     "type":"textarea","required":True,"max_length":6000,
                     "default":example_plan_text()},
                    {"name":"board_transform_json","label":"Explicit nominal board transform (16 row-major values, or null)",
                     "type":"textarea","required":True,"default":"null","max_length":1000},
                    {"name":"clearance_mm","label":"Nominal tip clearance (mm; not full-arm clearance)",
                     "type":"number","required":True,"default":5,"min":0.1,"max":100,"step":0.1},
                    _select("fault","Synthetic first-trial fault",
                        ("NONE","NO_RESPONSE","STALE","DISCONNECT","CANCELLED","OVERSHOOT","DRIFT","DROPOUT","MALFORMED"),"NONE")))
        for action_id,label in (
            ("movement_campaign_preview","Preview finite movement campaign (no hardware)"),
            ("movement_campaign_simulate","Simulate movement campaign (no hardware)"))
    ),
    *(
        ActionDefinition(
            action_id,
            label,
            "camera",
            description,
            "physical_usb_identity",
            timeout_s=timeout_s,
            mode="physical",
        )
        for action_id, label, description, timeout_s in (
            (
                "physical_usb_complete_assess",
                "Assess all four original USB phases",
                "File-only: reread baseline, absence, reconnect and reboot originals and retain an exact assessment. No acquisition, camera capture, arm access or movement.",
                180,
            ),
            (
                "physical_usb_complete_review",
                "Review final camera-identity assessment",
                "File-only: independently review the exact retained assessment. Acceptance covers camera identity only, never image calibration, capture, arm access or movement. Rejection is the default.",
                180,
            ),
            (
                "physical_usb_reboot_begin",
                "Begin reported host-restart interval",
                "Record the operator's manual Windows Restart report in a new launch after complete original reconnect evidence. An app restart is not a host reboot. No metadata, boot or USB acquisition.",
                120,
            ),
            (
                "physical_usb_reboot_prepare",
                "Prepare fresh after-reboot metadata and files",
                "Retain three newly logged and reviewed post-report metadata acquisitions in this launch and inspect only the fixed descriptor-query files. Refresh the original session explicitly after metadata acquisition.",
                180,
            ),
            (
                "physical_usb_reboot_review",
                "Review exact after-reboot subjects",
                "Independently review the original target, policy, fixed runtime and separate host-boot intent. Review performs no acquisition and authorizes no restart or device control.",
                120,
            ),
            (
                "physical_usb_reboot_boot_collect",
                "Observe after-reboot host boot once",
                "Run only the separately reviewed local boot observation. It must show the same host, a different boot after reconnect and before Begin. No USB query runs automatically; no restart command or attestation.",
                180,
            ),
            (
                "physical_usb_reboot_collect",
                "Collect after-reboot USB descriptors once",
                "Run one separately admitted descriptor query and retain original comparisons. Unknown effects remain unknown. No retry, full qualification PASS, camera capture, arm, power, motion or restart authority.",
                180,
            ),
            (
                "physical_usb_reconnect_begin",
                "Begin reported USB reconnect interval",
                "Record the operator's manual reconnect report after original physical-node absence. No metadata acquisition, boot observation, USB query or automatic reconnection.",
                120,
            ),
            (
                "physical_usb_reconnect_prepare",
                "Prepare fresh reconnect metadata and files",
                "Retain three newly logged and reviewed post-report metadata acquisitions in this launch and inspect only the fixed descriptor-query files.",
                180,
            ),
            (
                "physical_usb_reconnect_review",
                "Review exact reconnect subjects",
                "Independently review the retained current target, policy, fixed runtime and separate local boot intent. Review itself performs no acquisition.",
                120,
            ),
            (
                "physical_usb_reconnect_boot_collect",
                "Observe reconnect-phase host boot once",
                "Run only the separately reviewed local boot observation. A new app launch is not a reboot; clean same-boot retention does not automatically query USB.",
                180,
            ),
            (
                "physical_usb_reconnect_collect",
                "Collect reconnect USB descriptors once",
                "Run one separately admitted descriptor query and retain comparisons to the original unit. Unknown effects remain unknown. No retry, camera capture, arm, power, motion or restart authority.",
                180,
            ),
            (
                "physical_usb_absence_begin",
                "Begin reported USB unplug interval",
                "Record the operator report and inspect the exact baseline-derived physical-node target and fixed files. No automatic unplug, boot observation or presence query.",
                180,
            ),
            (
                "physical_usb_absence_boot_review",
                "Review absence host-boot scope",
                "Independently review the original local host-boot intent. This grants no USB, capture, arm or restart permission.",
                120,
            ),
            (
                "physical_usb_absence_boot_collect",
                "Observe absence-phase host boot once",
                "Run the separately reviewed local host-boot scope once. Only clean same-boot evidence prepares a later file-only presence review; no query runs automatically.",
                180,
            ),
            (
                "physical_usb_absence_runtime_review",
                "Review exact physical-node presence scope",
                "Review the retained baseline-derived physical USB target, operation, fixed runtime and bounded presence policy. No camera endpoint selection after unplugging.",
                120,
            ),
            (
                "physical_usb_absence_collect",
                "Query exact physical USB presence once",
                "Run one consumed-permit physical-node query and retain complete original outcomes. Unknown counts remain unknown; no retry, camera capture, arm, power or motion permission.",
                180,
            ),
            (
                "physical_usb_qualification_begin",
                "Begin new trial BASELINE",
                "Record the original phase boundary before fresh metadata acquisition. No boot observation or USB query.",
                120,
            ),
            (
                "physical_usb_qualification_prepare",
                "Prepare fresh BASELINE metadata and files",
                "Retain this launch's newly acquired and reviewed metadata with its logged acquisition interval and exact fixed USB runtime inspection.",
                180,
            ),
            (
                "physical_usb_qualification_review",
                "Review exact trial BASELINE subjects",
                "Independently review the retained target, policy, fixed runtime and separate original local boot request. No acquisition occurs.",
                120,
            ),
            (
                "physical_usb_qualification_collect",
                "Collect new trial BASELINE once",
                "First collect one original-requested local boot observation; only after clean retention request a separate bounded USB query. Unknown effects and partial attempts remain held; no retry, capture or arm authority.",
                180,
            ),
            (
                "physical_usb_qualification_declare",
                "Declare original USB qualification trial",
                "Save the original received-unit trial plan and declared cable/port labels. No USB query, host-boot observation, disconnect or restart is performed; the old baseline is not relabeled as trial evidence.",
                120,
            ),
            (
                "physical_usb_identity_inspect",
                "Inspect fixed USB identity files",
                "Inspect the fixed runtime and policy against the original reviewed camera identity. File-only inspection does not query USB, authorize capture or connect the arm.",
                120,
            ),
            (
                "physical_usb_identity_review",
                "Review exact USB baseline query",
                "Review the original fixed-file inspection, policy and exact target with a distinct procedural label. Review does not run a query or qualify the camera.",
                120,
            ),
            (
                "physical_usb_identity_collect",
                "Collect one controlled USB baseline",
                "Explicitly run one admitted, bounded USB descriptor query for the original target. Hub opens, reads and cleanup are retained; no camera frames, configuration writes or arm access. No automatic retry.",
                180,
            ),
            (
                "physical_usb_identity_export",
                "Export original USB evidence",
                "Copy the complete retained USB metadata family to a separate bounded diagnostic bundle, including held historical evidence. No query or replay is performed.",
                120,
            ),
        )
    ),
    *(
        ActionDefinition(
            action_id,
            label,
            "camera",
            description,
            "physical_camera_identity_records",
            timeout_s=120,
            mode="physical",
        )
        for action_id, label, description in (
            (
                "physical_camera_identity_submit",
                "Submit original camera identity metadata",
                "Retain the exact server-owned helper and native endpoint evidence with an explicit INT-018 observation or UNKNOWN reason. Metadata completeness does not qualify persistent identity or release capture.",
            ),
            (
                "physical_camera_identity_review",
                "Review exact original identity assessment",
                "A distinct procedural reviewer acknowledges or rejects the exact retained identity subject. Missing serial, USB and stability evidence remain BLOCKED; no stage-5 entry is issued.",
            ),
            (
                "physical_camera_identity_export",
                "Export original camera identity metadata bundle",
                "Export the complete bounded identity metadata family separately, including held historical subjects and exact coverage. No live metadata query, replay or native release occurs.",
            ),
        )
    ),
    *(
        ActionDefinition(
            action_id,
            label,
            "camera",
            description,
            "physical_received_camera",
            timeout_s=timeout,
            mode="physical",
        )
        for action_id, label, timeout, description in (
            (
                "physical_received_camera_files_discover",
                "Discover received-camera originals",
                60,
                "Read the guarded assigned inbox for opaque original-file choices. No selection, receipt submission or device observation is automatic.",
            ),
            (
                "physical_received_camera_draft_start",
                "Start or revise received-camera draft",
                60,
                "Explicitly choose a blank draft or revise the last original notebook. Carried observations retain their original provenance; no nominal values or acceptance are supplied.",
            ),
            (
                "physical_received_camera_draft_record",
                "Record received-camera draft observation",
                60,
                "Record one of the sixteen original questions with explicit value or UNKNOWN reason, method, evidence note and operator. Drafts do not accept measurements or a physical stage.",
            ),
            (
                "physical_received_camera_submit",
                "Submit received-camera originals and inspection",
                120,
                "Retain exact stage-3 notebook, selected original bytes and structured purchased-camera inspection. Fixed receipt checks do not release installation, native runtime or calibration.",
            ),
            (
                "physical_received_camera_review",
                "Review exact received-camera assessment",
                120,
                "A distinct procedural reviewer acknowledges or rejects the exact retained receipt subject. Review cannot invent missing observations or upgrade a blocked assessment.",
            ),
            (
                "physical_camera_identity_begin",
                "Request camera identity stage",
                120,
                "After reviewed stage-3 PASS, explicitly request identity-stage WAITING_OPERATOR. This does not enumerate a device, establish persistent identity or connect a camera.",
            ),
            (
                "physical_received_camera_export",
                "Export received-camera metadata bundle",
                120,
                "Write a separate bounded metadata bundle retaining every received-stage cycle and draft/attempt coverage. Private original media is not included; no replay or qualification is granted.",
            ),
        )
    ),
    *(
        ActionDefinition(
            action_id,
            label,
            "camera",
            description,
            "physical_static_camera_onboarding",
            timeout_s=timeout_s,
            mode="physical",
        )
        for action_id, label, timeout_s, description in (
            (
                "physical_static_contract_collect",
                "Collect original static-camera design contract",
                180,
                "Read the fixed architecture, purchased profile and support sources into the original stage-2 record. Design values are not received measurements; no installation or native camera release.",
            ),
            (
                "physical_static_contract_review",
                "Review exact static-camera design assessment",
                120,
                "Review the exact original design assessment with a distinct procedural label. Design-only PASS does not qualify installed hardware or enter the next stage automatically.",
            ),
            (
                "physical_camera_receipt_begin",
                "Request received-camera inspection stage",
                120,
                "After reviewed stage-2 PASS, explicitly request camera_receipt WAITING_OPERATOR in the original store. No received identity, measurement, connection or native operation is supplied.",
            ),
        )
    ),
    *(
        ActionDefinition(
            action_id,
            label,
            "camera",
            description,
            "physical_source_qualification",
            timeout_s=timeout_s,
            mode="physical",
        )
        for action_id, label, timeout_s, description in (
            (
                "physical_source_isolation_files_discover",
                "Discover isolation evidence originals",
                60,
                "Read the guarded assigned inbox for opaque original-file choices. No file is selected or imported automatically; discovery does not observe disconnected power.",
            ),
            (
                "physical_source_qualify",
                "Collect and assess source qualification",
                300,
                "Retain fresh source facts, a fixed hardware-free ownership experiment and an explicit isolation statement/original. UNKNOWN stays blocked. Save the exact source-only assessment for review; no native release or device activity.",
            ),
            (
                "physical_source_qualification_review",
                "Review exact source qualification",
                120,
                "A distinct procedural reviewer records the exact deterministic source assessment. Review cannot upgrade BLOCKED. A committed source-stage PASS does not qualify or release a camera or arm.",
            ),
            (
                "physical_static_contract_begin",
                "Request static-camera contract stage",
                120,
                "After reviewed source-stage PASS, explicitly request stage 2 WAITING_OPERATOR in the same original store. No stage-2 acceptance, camera activation, power or motion is performed.",
            ),
        )
    ),
    ActionDefinition(
        "physical_intake_files_discover",
        "Discover intake attachments",
        "camera",
        "Inspect bounded immediate files in the assigned intake inbox. Opaque choices identify that snapshot only; no submission, device activity or physical acceptance is automatic.",
        "physical_intake_evidence",
        timeout_s=30,
        mode="physical",
    ),
    ActionDefinition(
        "physical_intake_submit",
        "Submit intake evidence to the original store",
        "camera",
        "Retain all sixteen explicit observations and selected original attachment bytes. OBSERVED requires an attachment; UNKNOWN may omit it. Structure and byte integrity do not verify measurement truth or accept a physical stage.",
        "physical_intake_evidence",
        timeout_s=120,
        mode="physical",
        fields=(
            {
                "name": "operator_id",
                "label": "Submission operator label (not authenticated)",
                "type": "text",
                "required": True,
                "default": "",
                "max_length": 64,
            },
            {
                "name": "file_only",
                "label": "I consent to the exact file-only original-store submission; no device or physical acceptance",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
        ),
    ),
    ActionDefinition(
        "physical_intake_review",
        "Review exact intake submission",
        "camera",
        "Review the exact retained submission and completeness assessment with a distinct label. Acknowledgement is only for later-stage review; rejection preserves history. Neither rewrites the original BLOCKED source verdict.",
        "physical_intake_evidence",
        timeout_s=120,
        mode="physical",
        fields=(
            {
                "name": "reviewer_id",
                "label": "Distinct reviewer label (not authenticated independent people)",
                "type": "text",
                "required": True,
                "default": "",
                "max_length": 64,
            },
            {
                "name": "decision",
                "label": "Decision for this exact subject",
                "type": "select",
                "required": True,
                "options": [
                    {
                        "value": "ACKNOWLEDGE_FOR_LATER_STAGE_REVIEW",
                        "label": "Acknowledge for later-stage review only",
                    },
                    {"value": "REJECT", "label": "Reject; retain original evidence"},
                ],
            },
            {
                "name": "file_only",
                "label": "I consent to file-only procedural review, not physical acceptance",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
        ),
    ),
    ActionDefinition(
        "physical_intake_export_originals",
        "Export private intake originals (not redacted)",
        "camera",
        "Copy the exact retained original media to a fresh assigned export folder. Files may contain private material and are not redacted or converted; ordinary diagnostic exports contain metadata only.",
        "physical_intake_evidence",
        timeout_s=120,
        mode="physical",
        fields=(
            {
                "name": "include_private_originals",
                "label": "I explicitly consent to exporting potentially private original files WITHOUT redaction",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
            {
                "name": "file_only",
                "label": "I consent to this bounded original-file export only",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
        ),
    ),
    ActionDefinition(
        "physical_intake_start",
        "Start passive intake draft",
        "camera",
        "Create blank draft questions from the verified original camera requirements. No measurement, attachment, physical stage or device connection is accepted. Export drafts before closing; draft import is not yet available.",
        "physical_intake",
        mode="physical",
    ),
    ActionDefinition(
        "physical_intake_record",
        "Record or revise an intake draft entry",
        "camera",
        "Explicitly record an observation or an unknown with its reason. Evidence notes describe material to collect, not attached or verified bytes. Values remain unreviewed drafts; no canonical stage advances.",
        "physical_intake",
        mode="physical",
        fields=(
            {
                "name": "record_id",
                "label": "Build question",
                "type": "select",
                "required": True,
                "options": [],
            },
            _select(
                "observation_status",
                "Draft observation status",
                ("UNKNOWN", "OBSERVED"),
                "UNKNOWN",
            ),
            {
                "name": "observed_value",
                "label": "Observed value in the stated unit, or reason it is unknown",
                "type": "text",
                "required": True,
                "default": "",
                "max_length": 256,
            },
            {
                "name": "method",
                "label": "Instrument / method (or explicitly state not measured)",
                "type": "text",
                "required": True,
                "default": "",
                "max_length": 512,
            },
            {
                "name": "evidence_note",
                "label": "Evidence description only (or explicitly state not supplied)",
                "type": "textarea",
                "required": True,
                "default": "",
                "max_length": 1024,
            },
            {
                "name": "operator_id",
                "label": "Recording operator label (not authenticated identity)",
                "type": "text",
                "required": True,
                "default": "",
                "max_length": 64,
            },
        ),
    ),
    ActionDefinition(
        "physical_source_preflight",
        "Check actual source files (no devices)",
        "overview",
        "Create a separate durable source-only diagnostic session; check actual software/contracts/native build bytes and read back its full retained report. Does not enumerate or open hardware, observe power, complete a physical stage or enable motion. One attempt per launch; export before restarting.",
        "physical_preflight",
        timeout_s=120,
        mode="physical",
        fields=(
            {
                "name": "operator_id",
                "label": "Diagnostic operator ID",
                "type": "text",
                "required": True,
                "default": "setup-operator",
                "max_length": 64,
            },
        ),
    ),
    ActionDefinition(
        "rehearsal_discover",
        "Discover saved rehearsals",
        "commissioning",
        "Read bounded metadata beneath the assigned rehearsal folder. No storage qualification, session creation, device access, or automatic reopening occurs.",
        "commissioning",
        mode="rehearsal",
    ),
    ActionDefinition(
        "rehearsal_reopen",
        "Open selected saved rehearsal",
        "commissioning",
        "Requalify storage and inspect the original session under leases. Restore exact evidence only; no camera operation, prior approval, permit or command is replayed. Each selection can be attempted once per launch.",
        "commissioning",
        mode="rehearsal",
        fields=(_select("choice_id", "Discovered rehearsal session", (), ""),),
    ),
    ActionDefinition(
        "rehearsal_initialize",
        "Initialize durable rehearsal",
        "commissioning",
        "Create a separate Windows-qualified M1 rehearsal store and immutable REHEARSAL session. No physical session or device is created.",
        "commissioning",
        mode="rehearsal",
    ),
    ActionDefinition(
        "rehearsal_collect",
        "Collect due-stage synthetic evidence",
        "commissioning",
        "Collect only the due stage. Stages 7–8 retain synthetic intrinsics/pixel checks; 9 checks the arm profile with injected identity metadata; 10–11 assess synthetic power procedures; 13 checks nominal reference geometry and rigid fitting with held-out points. Camera stages and stage 12 wait for a separate, explicitly incapable campaign action. None opens hardware or energizes the arm. Missing evaluations hold on reopening; expected-fault checks never replace nominal acceptance or qualify installed calibration.",
        "commissioning",
        mode="rehearsal",
        fields=(
            {
                "name": "operator_id",
                "label": "Rehearsal operator ID",
                "type": "text",
                "required": True,
                "default": "rehearsal-operator",
                "max_length": 64,
            },
            _select(
                "candidate",
                "Synthetic candidate (used at camera identity stage only)",
                ("synthetic-b0477", "synthetic-wrong-camera"),
                "synthetic-b0477",
            ),
        ),
    ),
    ActionDefinition(
        "rehearsal_record_operator",
        "Record missing reopened-stage operator",
        "commissioning",
        "For an older uncollected camera stage only, explicitly retain its operator before new settings or a campaign. This does not recover or replay an earlier operation.",
        "commissioning",
        mode="rehearsal",
        fields=(
            {
                "name": "operator_id",
                "label": "Rehearsal operator ID",
                "type": "text",
                "required": True,
                "default": "rehearsal-operator",
                "max_length": 64,
            },
        ),
    ),
    ActionDefinition(
        "rehearsal_camera_settings",
        "Prepare synthetic camera settings",
        "commissioning",
        "Retain a fixed synthetic brightness setting before the mode campaign. This is a fixture knob, not a measured UVC exposure or gain control. Stage six reuses the reviewed setting.",
        "commissioning",
        mode="rehearsal",
        fields=(
            {
                "name": "brightness_offset",
                "label": "Synthetic brightness offset",
                "type": "number",
                "required": True,
                "default": 0,
                "min": -64,
                "max": 64,
            },
        ),
    ),
    ActionDefinition(
        "rehearsal_camera_campaign",
        "Run coordinated synthetic camera campaign",
        "commissioning",
        "Retain finite B0477-sized YUY2 fixtures, verify the binary dataset and derive its latest preview. Real storage leases and one-use arming protect the rehearsal. Pixels and device counters remain synthetic; optics and hardware are not qualified.",
        "commissioning",
        mode="rehearsal",
        fields=(
            {
                "name": "frame_count",
                "label": "Binary synthetic frames (about 40 MB each, plus retained copy)",
                "type": "number",
                "required": True,
                "default": 1,
                "min": 1,
                "max": 4,
            },
            _select(
                "fault",
                "Campaign scenario",
                ("none", "identity-mismatch", "cleanup-uncertain"),
                "none",
            ),
        ),
    ),
    ActionDefinition(
        "rehearsal_camera_probe",
        "Probe contained camera capabilities",
        "commissioning",
        "Run one finite incapable process to report modeled modes and electronic control ranges. Retain its complete bounded protocol before staging settings. No frames, control writes or hardware access; manual focus/aperture remain physical checks.",
        "commissioning",
        timeout_s=120,
        mode="rehearsal",
        fields=(
            _select(
                "fault",
                "Fixed probe scenario",
                (
                    "none",
                    "identity-mismatch",
                    "cleanup-uncertain",
                    "child-timeout",
                    "malformed-result",
                ),
                "none",
            ),
        ),
    ),
    ActionDefinition(
        "rehearsal_camera_configuration",
        "Stage reported camera mode and controls",
        "commissioning",
        "Choose an exact reported mode and bounded electronic intent. This saves immutable configuration only; no setting is applied until an explicitly prepared contained capture. Independent readback follows capture, not staging.",
        "commissioning",
        mode="rehearsal",
        fields=(_select("mode_choice_id", "Reported mode", (), ""),),
    ),
    ActionDefinition(
        "rehearsal_owned_camera_campaign",
        "Run contained incapable camera-process campaign",
        "commissioning",
        "Launch one owned, contained incapable child to produce source-derived native-format fixtures, retain the binary dataset and derive its preview. Actual OS process cleanup and synthetic native camera cleanup are separate evidence. Reserve about 85 MB per frame plus a storage margin. No physical camera, driver, USB3 link or capture backend is qualified.",
        "commissioning",
        timeout_s=120,
        mode="rehearsal",
        fields=(
            {
                "name": "frame_count",
                "label": "Contained fixture frames (about 85 MB each, plus margin)",
                "type": "number",
                "required": True,
                "default": 1,
                "min": 1,
                "max": 4,
                "step": 1,
            },
            _select(
                "fault",
                "Fixed contained-process fixture scenario",
                (
                    "none",
                    "identity-mismatch",
                    "cleanup-uncertain",
                    "child-timeout",
                    "malformed-result",
                    "control-readback-drift",
                ),
                "none",
            ),
        ),
    ),
    ActionDefinition(
        "rehearsal_arm_feedback_campaign",
        "Run coordinated memory-only arm feedback",
        "commissioning",
        "Run one exact feedback request through the existing arm worker and sealed in-memory serial backend. Bind reviewed identity/power inputs and retain the complete exchange before known sealing. Independently modeled post-campaign power is not inferred from serial close. No physical port, power or motion is used.",
        "commissioning",
        mode="rehearsal",
    ),
    ActionDefinition(
        "rehearsal_owned_arm_feedback_campaign",
        "Run contained incapable arm-feedback rehearsal",
        "commissioning",
        "Launch one fixed contained incapable child for the due feedback stage. Resolve fresh modeled Windows controller metadata before port open and again before the single feedback write, retaining both identity checks and the bounded non-purging serial exchange. Actual process cleanup, synthetic serial cleanup and the independent synthetic power observation remain separate. The parent budget is 20 seconds and the feedback line is bounded to 2048 bytes. No physical port, power, motion or arbitrary command is available; Stop holds without replay.",
        "commissioning",
        mode="rehearsal",
        fields=(
            _select(
                "scenario",
                "Fixed contained feedback scenario",
                (
                    "nominal",
                    "boot-bytes",
                    "short-write",
                    "timeout",
                    "identity-change",
                    "identity-change-preopen",
                    "malformed-metadata",
                    "close-failure",
                    "malformed-response",
                    "extra-response",
                    "child-timeout",
                    "malformed-result",
                ),
                "nominal",
            ),
        ),
    ),
    ActionDefinition(
        "rehearsal_assess",
        "Assess retained synthetic evidence",
        "commissioning",
        "Evaluate the exact current receipt, retain its assessment and request review. Assessment alone does not pass a stage.",
        "commissioning",
        mode="rehearsal",
    ),
    ActionDefinition(
        "rehearsal_review",
        "Review exact synthetic assessment",
        "commissioning",
        "Accept only the displayed, source/session/evidence-bound assessment as a distinct rehearsal reviewer. A blocked assessment remains blocked; this cannot pass physical stages.",
        "commissioning",
        mode="rehearsal",
        fields=(
            {
                "name": "reviewer_id",
                "label": "Distinct rehearsal reviewer ID",
                "type": "text",
                "required": True,
                "default": "rehearsal-reviewer",
                "max_length": 64,
            },
            {
                "name": "accept_assessment",
                "label": "I reviewed this exact synthetic assessment; it grants no physical authority",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
        ),
    ),
    ActionDefinition(
        "rehearsal_refresh",
        "Verify retained rehearsal state",
        "commissioning",
        "Explicitly verify the separate session, attempt ledger and global quarantine. No recovery, repair, camera or campaign replay occurs.",
        "commissioning",
        mode="rehearsal",
    ),
    ActionDefinition(
        "run_baseline",
        "Run setup baselines",
        "overview",
        "Check host dependencies, source alignment, inactive foundation and synthetic camera/arm connection. No device access.",
        "baseline",
        120,
    ),
    ActionDefinition(
        "boundary_tests",
        "Run software boundary tests",
        "overview",
        "Run the registered camera, serial, inventory and CLI unit-test suite in a bounded child process. No physical hardware is used.",
        "boundary_tests",
        120,
    ),
    ActionDefinition(
        "camera_profile",
        "Inspect purchased camera profile",
        "camera",
        "Read the pinned B0477 purchase profile. Actual unit, focus and driver compatibility remain unverified.",
        "camera_profile",
    ),
    ActionDefinition(
        "physical_camera_discover",
        "Discover saved camera setup records",
        "camera",
        "Inspect bounded original-store metadata in the assigned camera folder. No storage qualification, replacement, automatic selection or device access.",
        "physical_camera_setup",
        30,
        mode="physical",
        fields=(
            {
                "name": "operator_id",
                "label": "Setup operator ID",
                "type": "text",
                "required": True,
                "default": "setup-operator",
                "max_length": 64,
            },
        ),
    ),
    ActionDefinition(
        "physical_camera_mode_enter",
        "Continue to camera setup",
        "camera",
        "Reread the accepted original camera-identity review and record the mode/control setup stage as waiting for operator input. This does not open the camera, configure settings, initialize the arm or authorize movement. One attempt only.",
        "physical_camera_setup",
        180,
        mode="physical",
        fields=(
            {
                "name": "operator_id",
                "label": "Setup operator label (up to 64 UTF-8 bytes)",
                "type": "text",
                "required": True,
                "default": "setup-operator",
                "max_length": 64,
            },
            {
                "name": "file_only",
                "type": "checkbox",
                "required": True,
                "default": False,
                "label": "Record the next setup stage only; no camera, arm, power, motion or contact operation",
            },
        ),
    ),
    *(
        ActionDefinition(
            action_id,
            title,
            "camera",
            description,
            "physical_camera_setup",
            180,
            mode="physical",
            fields=(
                {
                    "name": "operator_id",
                    "label": "Operator/reviewer label (up to 64 UTF-8 bytes)",
                    "type": "text",
                    "required": True,
                    "default": "setup-operator",
                    "max_length": 64,
                },
                {
                    "name": "file_only",
                    "type": "checkbox",
                    "required": True,
                    "default": False,
                    "label": "Record preparation/review only; no camera access, arm startup, movement or contact",
                },
            ),
        )
        for action_id, title, description in (
            (
                "physical_camera_probe_prepare",
                "Prepare bounded camera probe",
                "Verify the original setup, current reviewed metadata and installed probe/capture files; retain the exact proposed probe without opening the camera. One attempt only.",
            ),
            (
                "physical_camera_probe_review",
                "Review prepared camera probe",
                "Reread and review the exact retained preparation in this launch. This records eligibility for later admission checks, not permission to open a camera. One attempt only.",
            ),
        )
    ),
    ActionDefinition(
        "physical_camera_probe_export",
        "Export camera probe preparation",
        "diagnostics",
        "Export full retained preparation/review and incomplete attempts to the assigned workspace folder. Hash-verified diagnostic copies never restore a connection or authorize replay.",
        "physical_camera_probe_export",
        120,
        mode="physical",
    ),
    ActionDefinition(
        "physical_camera_probe_attempt_export",
        "Export camera probe attempt",
        "diagnostics",
        "Export the complete cached admission, native run/supervision readback, queued intent and completion outcome. Uses the assigned export folder; never reopens hardware or replays an attempt.",
        "physical_camera_probe_attempt_export",
        120,
        mode="physical",
    ),
    ActionDefinition(
        "physical_camera_reopen",
        "Open selected original camera setup",
        "camera",
        "Explicitly audit the selected source-matching original store and restore its requirements. No prior metadata connection, camera setting, frame, approval or command is replayed.",
        "physical_camera_setup",
        240,
        mode="physical",
        fields=(
            {
                "name": "choice_id",
                "label": "Original camera setup store",
                "type": "select",
                "required": True,
                "options": [],
            },
            {
                "name": "operator_id",
                "label": "Setup operator ID",
                "type": "text",
                "required": True,
                "default": "setup-operator",
                "max_length": 64,
            },
        ),
    ),
    *tuple(
        ActionDefinition(
            action_id,
            label,
            "camera",
            description,
            "physical_camera_setup",
            240,
            mode="physical",
            fields=(
                {
                    "name": "operator_id",
                    "label": "Setup operator ID",
                    "type": "text",
                    "required": True,
                    "default": "setup-operator",
                    "max_length": 64,
                },
            ),
        )
        for action_id, label, description in (
            (
                "physical_camera_initialize",
                "Initialize camera-only setup records",
                "Explicitly create the assigned original camera diagnostic store with all physical stages pending. Qualify local storage only; no device inventory, camera or arm access.",
            ),
            (
                "physical_camera_refresh",
                "Verify original camera setup records",
                "Reopen and audit only this launch's original camera store. No replacement, recovery, stage acceptance or device replay occurs.",
            ),
            (
                "physical_camera_prerequisites",
                "Collect camera build prerequisites",
                "Read the four fixed build requirement sources and retain their complete document plus one initial eight-domain configuration record in original camera storage. Missing and later-stage values remain explicit. Record workspace-sources as waiting for operator evidence, not passed; no hardware observations are invented. One attempt per launch.",
            ),
        )
    ),
    *(
        ActionDefinition(
            action_id,
            label,
            "camera",
            description,
            "physical_camera_setup",
            240,
            mode="physical",
            fields=(
                {
                    "name": actor,
                    "label": actor.replace("_", " ").capitalize(),
                    "type": "text",
                    "required": True,
                    "max_length": 64,
                },
                {
                    "name": "file_only",
                    "label": "I confirm file-only evidence work; this does not establish disconnected power or authorize hardware.",
                    "type": "checkbox",
                    "required": True,
                },
            ),
        )
        for action_id, label, actor, description in (
            (
                "physical_camera_assess_sources",
                "Assess saved workspace sources",
                "operator_id",
                "Collect bounded actual source facts, save receipt and BLOCKED assessment, then commit original workspace-sources REVIEW_PENDING. No device access or physical acceptance.",
            ),
            (
                "physical_camera_review_sources",
                "Review exact workspace-source assessment",
                "reviewer_id",
                "Use a different reviewer label to acknowledge exact saved evidence and commit original workspace-sources BLOCKED. Labels are procedural, not authenticated independent people. No override or PASS.",
            ),
        )
    ),
    *(
        ActionDefinition(
            action_id,
            label,
            "camera",
            description,
            "physical_camera_runtime",
            mode="physical",
            fields=(
                {
                    "name": actor,
                    "label": actor.replace("_", " ").capitalize(),
                    "type": "text",
                    "required": True,
                    "max_length": 64,
                },
                {
                    "name": acknowledgement,
                    "label": "File diagnostics only; no runtime registration or device access",
                    "type": "checkbox",
                    "required": True,
                    "default": False,
                },
            ),
        )
        for action_id, label, description, actor, acknowledgement in (
            (
                "physical_camera_runtime_inspect",
                "Inspect installed camera runtime files",
                "Read only the fixed probe/capture executables, build records and closed source/artifact roster. Preserve mismatches and unknowns; never execute a helper, register a runtime or open a device.",
                "operator_id",
                "file_inspection_only",
            ),
            (
                "physical_camera_runtime_review",
                "Review exact camera runtime report",
                "A distinct reviewer label acknowledges the retained file report, including held gaps. No files are reinspected and no hardware or native runtime is qualified or enabled.",
                "reviewer_id",
                "file_review_only",
            ),
        )
    ),
    ActionDefinition(
        "physical_camera_plan",
        "Prepare physical camera acquisition plan",
        "camera",
        "Bind current reviewed endpoint metadata and separate dormant probe/capture runtime candidates to an exact intent. Show missing requirements without inspecting or opening hardware. Planning success is not acquisition approval.",
        "physical_camera",
        mode="physical",
        fields=(
            _select(
                "operation", "Planned camera operation", ("probe", "capture"), "probe"
            ),
            {
                "name": "operator_id",
                "label": "Planning operator ID",
                "type": "text",
                "required": True,
                "default": "setup-operator",
                "max_length": 64,
            },
        ),
    ),
    ActionDefinition(
        "physical_camera_probe",
        "Probe physical camera capabilities",
        "camera",
        "Run one bounded, identity-bound native capability probe after original setup authentication and fresh runtime/capacity checks. May open the selected camera; no control writes, images, arm startup or motion. No automatic retry.",
        "physical_camera",
        300,
        mode="physical",
        fields=(
            {
                "name": "operator_id",
                "label": "Current operator label (up to 64 UTF-8 bytes)",
                "type": "text",
                "required": True,
                "max_length": 64,
            },
            {
                "name": "arm_actuator_supply_disconnected",
                "label": "I have disconnected the arm actuator supply; this is my current report, not a measured power state",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
            {
                "name": "bounded_probe_consent",
                "label": "Run this single selected-camera probe; no camera settings changes, images, arm access or automatic retry",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
        ),
    ),
    ActionDefinition(
        "physical_camera_operating_proposal",
        "Record an operating-mode proposal (draft)",
        "camera",
        "Record why the currently logged camera mode should be used. An 8-fps proposal needs an explicit exception rationale. Reads the fixed purchase profile and writes diagnostic logs only; no original-stage approval, camera access or arm action.",
        "physical_camera_operating_proposal",
        30,
        mode="physical",
        fields=(
            {
                "name": "operator_id",
                "label": "Proposal operator label",
                "type": "text",
                "required": True,
                "max_length": 64,
            },
            {
                "name": "rationale",
                "label": "Why use the currently staged operating mode?",
                "type": "text",
                "required": True,
                "max_length": 1024,
            },
            {
                "name": "variance_rationale",
                "label": "For 8 fps: explain the exception to the 9-fps purchase reference (leave empty for 9 fps)",
                "type": "text",
                "required": False,
                "max_length": 1024,
                "default": "",
            },
        ),
    ),
    ActionDefinition(
        "physical_camera_operating_assessment",
        "Check proposal against saved original evidence",
        "camera",
        "Read original setup, probe and explicitly selected settings captures. Verify saved single-frame pixels against their retained logged checksums where available. Retain missing checks; no camera access, settings changes, stage approval or arm action.",
        "physical_camera_operating_assessment",
        300,
        mode="physical",
    ),
    ActionDefinition(
        "physical_camera_operating_submit",
        "Save camera originals for separate review",
        "camera",
        "Reread the logged proposal and two explicitly selected sealed captures. Save one immutable original submission and verify its REVIEW_PENDING transition. No camera access, settings changes, stage approval or arm action; partial outcomes are never replayed.",
        "physical_camera_operating_submit",
        300,
        mode="physical",
    ),
    ActionDefinition(
        "physical_camera_configuration_capture",
        "Verify settings with one camera frame",
        "camera",
        "Apply the explicitly staged reported mode and electronic controls, read them back and capture one bounded frame using original setup admission. No calibration, stage acceptance, arm access or automatic retry.",
        "physical_camera",
        300,
        mode="physical",
        fields=(
            {
                "name": "operator_id",
                "label": "Current operator label (up to 64 UTF-8 bytes)",
                "type": "text",
                "required": True,
                "max_length": 64,
            },
            {
                "name": "arm_actuator_supply_disconnected",
                "label": "The arm actuator supply is disconnected now; this is my report, not a measured power state",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
            {
                "name": "bounded_configuration_capture_consent",
                "label": "Apply these camera settings, read them back and capture one bounded frame; no arm access or automatic retry",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
        ),
    ),
    ActionDefinition(
        "physical_camera_configuration_attempt_export",
        "Export camera settings-capture attempt",
        "camera",
        "Export one selected cached attempt including queue, original admission, readback, cleanup and completion. No device access, image pixels, admission restoration or replay.",
        "physical_camera_configuration_attempt_export",
        120,
        mode="physical",
        fields=(
            {
                "name": "attempt_choice_id",
                "label": "Retained settings-capture attempt",
                "type": "select",
                "required": True,
                "options": [],
            },
        ),
    ),
    ActionDefinition(
        "physical_camera_capture",
        "Capture a physical camera frame",
        "camera",
        "Reserved for separately admitted finite native capture and verified frame publication. Last captured frame, not an unbounded live stream.",
        "physical_camera",
        mode="physical",
        hold="Capture remains held pending original settings/capture admission and stage qualification. A completed probe does not authorize capture, arm power or motion.",
    ),
    ActionDefinition(
        "camera_rehearsal",
        "Rehearse camera connection",
        "camera",
        "Exercise identity, mode, settings, freshness and cleanup with incapable providers, including a selected fault.",
        "connection_rehearsal",
        fields=(_select("fault", "Scenario", CAMERA_FAULTS, "none"),),
        mode="rehearsal",
    ),
    ActionDefinition(
        "board_preview",
        "Show simulated placemat",
        "camera",
        "Render the source-bound nominal board and target locations. This is a schematic, not a physical camera frame.",
        "board_preview",
        mode="rehearsal",
    ),
    ActionDefinition(
        "prebuild_vision_checks",
        "Run pre-build vision checks (no devices)",
        "camera",
        "Run synthetic marker detection/tag loss and all six camera connection scenarios in one report. Expected fault rejection is success. No camera/arm access, lens adjustment, installed calibration or physical stage pass; export results in Diagnostics & exports.",
        "prebuild_vision_checks",
        120,
    ),
    ActionDefinition(
        "camera_stack",
        "Test static camera stack",
        "camera",
        "Cross-check the synthetic camera, UVC and intrinsics stack, including normal and tag-loss image observations.",
        "camera_stack",
        120,
        mode="rehearsal",
    ),
    ActionDefinition(
        "camera_connect",
        "Connect physical camera",
        "camera",
        "Reserved for the qualified native camera campaign; no numeric webcam fallback.",
        "unavailable",
        hold=PHYSICAL_HOLD,
    ),
    ActionDefinition(
        "physical_camera_configuration",
        "Stage reported native camera settings",
        "camera",
        "Choose only modes and electronic controls from the exact retained native probe. Stages immutable intent; does not apply settings, run a capture or pass a physical stage. Manual focus/aperture remain physical adjustments.",
        "physical_camera_configuration",
        30,
        mode="physical",
        fields=(
            {
                "name": "mode_choice_id",
                "label": "Reported native mode",
                "type": "select",
                "required": True,
                "options": [],
            },
            {
                "name": "operator_id",
                "label": "Settings operator label",
                "type": "text",
                "required": True,
                "max_length": 64,
            },
        ),
    ),
    ActionDefinition(
        "arm_rehearsal",
        "Rehearse arm handshake",
        "arm",
        "Use the exact feedback-only synthetic lifecycle. A blocked injected fault is an expected test outcome, not a real controller fault.",
        "connection_rehearsal",
        fields=(_select("fault", "Scenario", ARM_FAULTS, "none"),),
        mode="rehearsal",
    ),
    ActionDefinition(
        "rehearse_passive_arm_connection",
        "Rehearse passive USB connection",
        "arm",
        "Run one contained hardware-incapable child. All serial observations and isolation references are synthetic; no port opens. Retain its request, raw output and cleanup diagnostics for export. One attempt per launch; export before closing the application.",
        "passive_arm_rehearsal",
        timeout_s=30,
        mode="rehearsal",
        fields=(
            _select(
                "scenario",
                "Synthetic scenario",
                (
                    "lifecycle-nominal",
                    "lifecycle-open-failed",
                    "lifecycle-cleanup-unknown",
                    "nominal",
                    "open-failed",
                    "cleanup-unknown",
                    "malformed",
                    "wrong-binding",
                    "stall",
                ),
                "nominal",
            ),
        ),
    ),
    ActionDefinition(
        "inspect_passive_arm_history",
        "Inspect saved passive arm attempt",
        "arm",
        "Read one named session in the assigned diagnostic folder. Historical file verification only: no reconnect, replay, repair, power change or commissioning approval.",
        "passive_arm_history",
        timeout_s=30,
        fields=(
            {
                "name": "session_id",
                "label": "Saved wizard session ID",
                "type": "text",
                "required": True,
                "default": "",
                "max_length": 39,
            },
        ),
    ),
    ActionDefinition(
        "inspect_powered_feedback_history",
        "Inspect saved powered feedback attempt",
        "arm",
        "Read one named powered-feedback attempt from the assigned diagnostic folder. Missing or partial records are preserved as historical evidence. This cannot reconnect, replay, repair, verify cleanup or authorize motion.",
        "powered_feedback_history",
        timeout_s=30,
        fields=(
            {
                "name": "attempt_id",
                "label": "Saved operation ID",
                "type": "text",
                "required": True,
                "max_length": 42,
            },
        ),
    ),
    ActionDefinition(
        "inspect_physical_passive_history",
        "Inspect saved physical passive attempt",
        "arm",
        "Read the named physical attempt from this wizard's assigned log folder, including partial records. Historical diagnostics only; never reconnect, replay, repair, or establish current setup.",
        "physical_passive_history",
        timeout_s=30,
        fields=(
            {
                "name": "attempt_id",
                "label": "Saved operation ID",
                "type": "text",
                "required": True,
                "max_length": 42,
            },
        ),
    ),
    ActionDefinition(
        "run_powered_arm_feedback",
        "Run one supervised powered feedback query",
        "arm",
        "Use fresh powered startup and reviewed USB metadata for one T105 feedback query. Opening USB serial can reset the controller and cause startup movement. No motion, home, initialization or torque commands are sent. Export afterward; Stop is not an emergency stop.",
        "powered_arm_feedback",
        mode="physical",
        timeout_s=30,
        fields=(
            {
                "name": "firmware_unchanged",
                "label": "Firmware remains unchanged since delivery",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
        ),
    ),
    ActionDefinition(
        "capture_powered_arm_telemetry",
        "Capture arm telemetry (no commands)",
        "arm",
        "Read existing robot telemetry for up to five seconds using fresh powered setup and reviewed USB identity. Sends zero commands. Opening USB can reset the controller and cause startup movement. Samples are unsolicited or buffered, not replies to a new query. Export afterward; Stop is not an emergency stop.",
        "powered_arm_telemetry",
        mode="physical",
        timeout_s=30,
        fields=({"name": "firmware_unchanged", "label": "Firmware remains unchanged since delivery",
                 "type": "checkbox", "required": True, "default": False},),
    ),
    ActionDefinition(
        "run_passive_arm_connection",
        "Run supervised passive arm test",
        "arm",
        "Use the fresh USB-only setup for one supervised zero-write serial observation. Opening USB serial can reset the controller or change control lines. No motion, initialization, home or torque commands are sent. Export diagnostics afterward. Stop is not an emergency stop.",
        "passive_arm_connection",
        timeout_s=30,
        mode="physical",
    ),
    ActionDefinition(
        "rehearse_powered_arm_feedback",
        "Rehearse powered feedback (no hardware)",
        "arm",
        "Exercise one synthetic feedback query and failure handling. No serial port is opened. Export logs to preserve complete simulated evidence; this does not qualify the connected arm.",
        "powered_feedback_rehearsal",
        timeout_s=30,
        mode="rehearsal",
        fields=(
            _select(
                "scenario",
                "Synthetic scenario",
                (
                    "nominal",
                    "stale-input",
                    "incomplete-reply",
                    "short-write",
                    "cleanup-unknown",
                ),
                "nominal",
            ),
        ),
    ),
    ActionDefinition(
        "record_powered_arm_startup",
        "Record powered arm startup",
        "arm",
        "Record operator-reported adapter power, stable startup and USB reconnect. This invalidates USB-only setup in this session; it does not open a port, measure voltage or authorize feedback/motion.",
        "powered_arm_startup",
        mode="physical",
        timeout_s=30,
        fields=(
            {
                "name": "operator_id",
                "label": "Operator ID",
                "type": "text",
                "required": True,
                "max_length": 64,
            },
            {
                "name": "adapter_on",
                "label": "Supplied external adapter connected and arm switch ON",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
            {
                "name": "usb_connected",
                "label": "USB reconnected",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
            {
                "name": "secured_and_clear",
                "label": "Arm secured and movement area clear",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
            {
                "name": "stationary",
                "label": "Arm stationary without shaking or persistent grinding",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
            _select(
                "startup_motion",
                "Movement during startup",
                ("observed", "not_observed", "unknown"),
                "unknown",
            ),
        ),
    ),
    ActionDefinition(
        "record_passive_arm_setup",
        "Record USB-only arm setup",
        "arm",
        "Save current operator setup reports with the exact reviewed USB metadata and approved design review. This does not open a serial port or enable movement.",
        "passive_arm_setup",
        timeout_s=30,
        mode="physical",
        fields=(
            {
                "name": "operator_id",
                "label": "Operator ID",
                "type": "text",
                "required": True,
                "max_length": 64,
            },
            {
                "name": "power_disconnected",
                "label": "External adapter is disconnected; USB only",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
            {
                "name": "secured_and_clear",
                "label": "Arm is secured and its movement radius is clear",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
        ),
    ),
    ActionDefinition(
        "arm_feedback_contract",
        "Test one-shot arm feedback worker",
        "arm",
        "Exercise the new identity-bound onboarding worker with a sealed incapable serial backend. Inspect the nominal or injected-fault lifecycle, exact one-write limit and cleanup. Passing tests do not connect the arm or clear physical provider holds.",
        "arm_feedback_contract",
        fields=(
            _select(
                "scenario",
                "Incapable serial scenario",
                (
                    "nominal",
                    "boot-bytes",
                    "short-write",
                    "timeout",
                    "identity-change",
                    "close-failure",
                ),
                "nominal",
            ),
        ),
        mode="rehearsal",
    ),
    ActionDefinition(
        "rehearse_device_inventory",
        "Rehearse device discovery and selection",
        "camera",
        "Load fixed injected camera/serial metadata for the same explicit candidate-review workflow. No host inventory is read. Missing, duplicated or incomplete identities remain visible holds, not received-hardware facts.",
        "inventory_fixture",
        mode="rehearsal",
        fields=(
            _select(
                "scenario",
                "Metadata fixture scenario",
                (
                    "nominal",
                    "missing-identity",
                    "duplicate-identity",
                    "partial-inventory",
                ),
                "nominal",
            ),
        ),
    ),
    *(
        ActionDefinition(
            action_id,
            label,
            section,
            "Review one exact candidate from the last explicit metadata snapshot. This records a diagnostic acknowledgement only: not a persistent binding, device connection, received-model verification or permission to open hardware. A new inventory invalidates both reviews.",
            "device_selection",
            fields=(
                {
                    "name": "choice_id",
                    "label": "Observed metadata candidate",
                    "type": "select",
                    "required": True,
                    "options": [],
                },
                {
                    "name": "reviewer_id",
                    "label": "Metadata reviewer ID",
                    "type": "text",
                    "required": True,
                    "max_length": 64,
                },
                {
                    "name": "metadata_only",
                    "label": "I reviewed this metadata candidate only; it is not connected or qualified",
                    "type": "checkbox",
                    "required": True,
                    "default": False,
                },
            ),
        )
        for action_id, label, section in (
            ("review_camera_candidate", "Review camera metadata candidate", "camera"),
            ("review_arm_candidate", "Review arm metadata candidate", "arm"),
        )
    ),
    ActionDefinition(
        "inventory_devices",
        "Inspect attached device metadata",
        "arm",
        "Explicitly enumerate OS camera/serial metadata without opening either endpoint. This does not qualify or connect a device.",
        "inventory",
        mode="physical",
        fields=(
            {
                "name": "power_disconnected",
                "label": "Optional report: actuator power is disconnected (not required for metadata-only inspection)",
                "type": "checkbox",
                "required": False,
                "default": False,
            },
            {
                "name": "metadata_only",
                "label": "Inspect OS metadata only; do not open devices or send commands",
                "type": "checkbox",
                "required": False,
                "default": False,
            },
        ),
    ),
    ActionDefinition(
        "inspect_native_arm_metadata",
        "Inspect native arm identity metadata",
        "arm",
        "Compare the reviewed serial candidate with fresh Windows COM-interface and driver metadata in a bounded child. No port is opened; model, firmware, power and physical qualification remain unverified.",
        "native_arm_metadata",
        timeout_s=20,
        mode="physical",
        fields=(
            {
                "name": "power_disconnected",
                "label": "Optional report: actuator power is disconnected; not electrical verification",
                "type": "checkbox",
                "required": False,
                "default": False,
            },
            {
                "name": "metadata_only",
                "label": "Inspect metadata only; do not open the serial port or send commands",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
        ),
    ),
    ActionDefinition(
        "rehearse_native_arm_metadata",
        "Rehearse native arm identity correlation",
        "arm",
        "Run an incapable native-metadata fixture through the same decoder and reviewed-candidate comparison. No OS metadata, driver, serial port or hardware is accessed.",
        "native_arm_metadata_fixture",
        timeout_s=20,
        mode="rehearsal",
        fields=(
            _select(
                "scenario",
                "Simulated metadata outcome",
                (
                    "nominal",
                    "missing-fields",
                    "duplicate-mapping",
                    "changed-device",
                    "incomplete",
                ),
                "nominal",
            ),
            {
                "name": "metadata_only",
                "label": "Use incapable metadata fixtures only; this cannot connect or qualify the arm",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
        ),
    ),
    ActionDefinition(
        "camera_helper_inspect",
        "Inspect camera metadata helper files",
        "camera",
        "Inspect the fixed metadata-only helper catalog and its bounded file hashes without launching an executable or querying devices. Rehearsal uses incapable inspection fixtures. A missing or changed file remains a hold; an old build record is not runtime approval.",
        "camera_helper_registration",
        fields=(
            {
                "name": "operator_id",
                "label": "Helper inspection operator ID",
                "type": "text",
                "required": True,
                "max_length": 64,
            },
            {
                "name": "metadata_only",
                "label": "Inspect helper files only; do not launch the helper or access hardware",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
        ),
    ),
    ActionDefinition(
        "camera_helper_review",
        "Review metadata-only helper registration",
        "camera",
        "Review the retained helper inspection for this launch. Matching files can register only inventory and identity lookup; source activation, probe, capture and all arm actions stay unavailable. Distinct operator/reviewer labels record procedure, not authenticated independent people.",
        "camera_helper_registration",
        fields=(
            {
                "name": "reviewer_id",
                "label": "Helper reviewer ID (different from inspection operator)",
                "type": "text",
                "required": True,
                "max_length": 64,
            },
            {
                "name": "metadata_only",
                "label": "Register metadata lookup only; this does not qualify or activate hardware",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
        ),
    ),
    ActionDefinition(
        "native_camera_inventory",
        "Discover native camera endpoints",
        "camera",
        "Enumerate exact Media Foundation endpoint metadata for the explicitly reviewed camera snapshot. Rehearsal uses incapable fixtures; physical metadata requires a separately registered provider. No camera activation, mode probe or automatic selection occurs.",
        "native_camera_metadata",
        fields=(
            {
                "name": "metadata_only",
                "label": "Metadata lookup only; this does not activate or qualify the camera",
                "type": "checkbox",
                "required": True,
                "default": False,
            },
        ),
    ),
    *(
        ActionDefinition(
            action_id,
            label,
            "camera",
            description,
            "native_camera_metadata",
            fields=(
                {
                    "name": "choice_id",
                    "label": "Native endpoint metadata candidate",
                    "type": "select",
                    "required": True,
                    "options": [],
                },
                *(
                    (
                        {
                            "name": "reviewer_id",
                            "label": "Native metadata reviewer ID",
                            "type": "text",
                            "required": True,
                            "max_length": 64,
                        },
                    )
                    if action_id == "native_camera_review"
                    else ()
                ),
                {
                    "name": "metadata_only",
                    "label": "I understand this is endpoint metadata, not a connected or qualified camera",
                    "type": "checkbox",
                    "required": True,
                    "default": False,
                },
            ),
        )
        for action_id, label, description in (
            (
                "native_camera_identity",
                "Resolve selected native endpoint identity",
                "Query bounded SetupAPI/Configuration Manager metadata for exactly one server-selected endpoint. Compare its device instance and container with the reviewed generic camera; preserve missing or conflicting observations. A new query retires the old identity review before dispatch.",
            ),
            (
                "native_camera_review",
                "Review native endpoint mapping",
                "Review the exact retained endpoint identity and generic-camera match. A prospective endpoint binding is not persistent-unit qualification, camera activation, received-model verification or physical authority.",
            ),
        )
    ),
    ActionDefinition(
        "arm_connect",
        "Connect physical arm",
        "arm",
        "Reserved for separately reviewed power/startup and one-shot feedback qualification.",
        "unavailable",
        hold=PHYSICAL_HOLD,
    ),
    ActionDefinition(
        "calibration_rehearsal",
        "Rehearse camera calibration",
        "board",
        "Validate sealed synthetic acquisition, native-mode and held-out intrinsics contracts. No installed calibration is promoted.",
        "calibration_rehearsal",
        mode="rehearsal",
    ),
    ActionDefinition(
        "plan_task",
        "Compile a typing task",
        "tasks",
        "Compile individual keyboard key targets or Android tap targets. The result is semantic planning only and is never sent to hardware.",
        "plan_task",
        fields=(DEVICE_FIELD, TEXT_FIELD),
    ),
    ActionDefinition(
        "simulate_task",
        "Simulate a short typing task",
        "tasks",
        "Run existing nominal geometry, IK and vision checks for up to eight characters. Physical motion and contact remain blocked.",
        "simulate_task",
        240,
        fields=(DEVICE_FIELD, {**TEXT_FIELD, "default": "hi", "max_length": 8}),
        mode="rehearsal",
    ),
    ActionDefinition(
        'rehearse_static_task', 'Rehearse static-camera typing/tapping route', 'tasks',
        'Simulation only: static Arducam inputs, nominal targets and dense sequential IK. No devices or movement. Export logs to retain the full route evidence.',
        'static_task_rehearsal_parent', timeout_s=240,
        fields=(DEVICE_FIELD, {**TEXT_FIELD, 'default':'a', 'max_length':8},
                _select('park', 'Simulation park (board mm, not installed coordinates)',
                        ('nominal', 'overlay_290_40'), 'overlay_290_40'))),
    ActionDefinition(
        "execute_task",
        "Execute on hardware",
        "tasks",
        "A later independently qualified executor will own physical typing and tapping.",
        "unavailable",
        hold="Live motion/contact executor and received-unit calibration are not released. Simulation cannot enable this action.",
    ),
    ActionDefinition(
        "verify_v2",
        "Verify existing M1 storage",
        "diagnostics",
        "Read-only verification of the configured cell's existing M1 deployment; does not initialize storage or open devices.",
        "verify_v2",
    ),
    ActionDefinition(
        "record_note",
        "Record issue or resolution note",
        "diagnostics",
        "Append a diagnostic note. Notes do not clear physical holds or turn a failed test into a pass.",
        "note",
        fields=(
            {
                "name": "note",
                "label": "Issue, investigation or resolution",
                "type": "textarea",
                "required": True,
                "default": "",
                "max_length": 2000,
            },
        ),
    ),
    ActionDefinition(
        "export_logs",
        "Export diagnostic report",
        "diagnostics",
        "Write a new verified report, event log and manifest beneath the assigned export folder. Existing exports are never overwritten.",
        "export",
    ),
    ActionDefinition(
        "stop_operation",
        "Stop current diagnostic",
        "diagnostics",
        "Request bounded child-process cancellation. This is not an emergency stop or proof of robot power-off.",
        "stop",
    ),
)
# These historical live actions do not consume a reviewed, unit-bound motion
# capability. Keep their definitions for reading old diagnostic records, but
# do not expose or dispatch them as current wizard actions.
_UNREVIEWED_LIVE_MOTION_ACTIONS = frozenset({
    item.action_id for item in ACTIONS
    if item.action_id.startswith("run_wifi_roll_")
} | {"run_micro_commissioning"})
ACTIONS = tuple(
    item for item in ACTIONS
    if item.action_id not in _UNREVIEWED_LIVE_MOTION_ACTIONS
)
ACTION_BY_ID = {item.action_id: item for item in ACTIONS}


def validate_action_input(
    action: ActionDefinition, supplied: Mapping[str, Any]
) -> dict[str, Any]:
    if type(supplied) is not dict:
        raise WizardError("INVALID_INPUT", "Action input must be a JSON object.")
    names = {field["name"] for field in action.fields}
    if set(supplied) - names:
        raise WizardError(
            "UNKNOWN_INPUT_FIELD", "The action includes an unsupported field."
        )
    result: dict[str, Any] = {}
    for field in action.fields:
        name = field["name"]
        value = supplied.get(name, field.get("default"))
        if field["type"] == "checkbox":
            if type(value) is not bool or (field.get("required") and value is not True):
                raise WizardError("CONFIRMATION_REQUIRED", str(field["label"]))
        elif field["type"] == "select":
            if type(value) is not str or value not in {
                item["value"] for item in field["options"]
            }:
                raise WizardError("INVALID_SELECTION", str(field["label"]))
        elif field["type"] == "number":
            if type(value) not in (int, float):
                raise WizardError("INVALID_NUMBER", str(field["label"]))
            if field.get("step") == 1 and type(value) is not int:
                raise WizardError("INVALID_NUMBER", "Enter a whole-number count.")
            number = cast(int | float, value)
            try:
                finite = math.isfinite(number)
            except OverflowError:
                finite = False
            if not finite:
                raise WizardError("INVALID_NUMBER", str(field["label"]))
            if ("min" in field and number < field["min"]) or (
                "max" in field and number > field["max"]
            ):
                raise WizardError("NUMBER_OUT_OF_RANGE", str(field["label"]))
        else:
            empty_explicit_unknown = (
                (
                    action.action_id == "physical_source_qualify"
                    and name == "isolation_statement"
                    or action.action_id == "physical_camera_operating_proposal"
                    and name == "variance_rationale"
                    or action.action_id == "record_observational_movement"
                    and name == "detail"
                    or action.action_id == "physical_received_camera_submit"
                    and name
                    in {
                        "observed_manufacturer",
                        "observed_product_id",
                        "observed_camera_serial",
                        "observed_lens_focal_length_mm",
                    }
                )
                and field.get("required") is False
                and value == ""
            )
            if (
                type(value) is not str
                or (not value.strip() and not empty_explicit_unknown)
                or len(value) > field.get("max_length", 256)
            ):
                raise WizardError(
                    "INVALID_TEXT",
                    f"{field['label']}: enter 1–{field.get('max_length', 256)} characters.",
                )
            if any(ord(char) < 32 and char not in "\n\t" for char in value):
                raise WizardError("INVALID_TEXT", "Control characters are not allowed.")
        result[name] = value
    # Discovery never opens an endpoint. Accept the legacy power-off
    # acknowledgement, or an explicit metadata-only acknowledgement for a
    # powered setup. Neither grants serial-open or motion permission.
    if action.action_id == "inventory_devices" and not (
        result["metadata_only"] or result["power_disconnected"]
    ):
        raise WizardError("CONFIRMATION_REQUIRED", "Confirm metadata-only inspection.")
    if action.worker == 'first_motion_measurements_parent':
        from .first_motion_measurements import validate_measurements
        try:
            validate_measurements(result)
        except (ValueError,TypeError) as error:
            raise WizardError('INVALID_FIRST_MOTION_MEASUREMENTS',str(error)) from error
    if action.worker == 'first_motion_review':
        from .first_motion_contract import review_first_motion_request
        try:
            review_first_motion_request(result['request_json'])
        except (ValueError,TypeError) as error:
            raise WizardError('INVALID_FIRST_MOTION_REVIEW',str(error)) from error
    if action.worker == 'movement_endpoint_rehearsal':
        from .wizard_endpoint_rehearsal import validate_rehearsal
        try:
            validate_rehearsal(result)
        except (ValueError, TypeError) as error:
            raise WizardError('INVALID_ENDPOINT_REHEARSAL', str(error)) from error
    if action.worker == 'endpoint_request_review':
        from .wizard_endpoint_review import review_endpoint_request
        try:
            review_endpoint_request(result['request_json'])
        except (ValueError,TypeError) as error:
            raise WizardError('INVALID_ENDPOINT_REVIEW',str(error)) from error
    if action.worker == 'endpoint_campaign_review_parent':
        from .endpoint_campaign_import import parse_campaign_review_input
        try:
            parse_campaign_review_input(result)
        except (ValueError,TypeError) as error:
            raise WizardError('INVALID_ENDPOINT_CAMPAIGN_REVIEW',str(error)) from error
    if action.worker in ('endpoint_engineering_intake_parent', 'first_motion_engineering_intake_parent'):
        if action.worker == 'first_motion_engineering_intake_parent':
            from .first_motion_review_intake import parse_decision
        else:
            from .wizard_engineering_review_intake import parse_decision
        try:
            # Structural preview only; execution records the real host time.
            parse_decision(result,now_ns=1)
        except (ValueError,TypeError) as error:
            raise WizardError('INVALID_ENGINEERING_DECISION',str(error)) from error
    if action.worker == 'positional_campaign_rehearsal':
        from rocell.motion.positional_campaign import compile_wrist_campaign
        try:
            compile_wrist_campaign(result['pattern'],int(result['leg_count']))
            if int(result['fault_leg']) > int(result['leg_count']):
                raise ValueError('Fault leg exceeds campaign length')
        except ValueError as error:
            raise WizardError('INVALID_POSITIONAL_CAMPAIGN',str(error)) from error
    if action.worker == "movement_campaign":
        from .wizard_movement_campaign import parse_plan, parse_transform
        try:
            plan = parse_plan(result["plan_json"])
            parse_transform(result["board_transform_json"],plan.to_dict()["frame"])
        except (ValueError, TypeError) as error:
            raise WizardError("INVALID_CAMPAIGN", str(error)) from error
    if action.worker == 'movement_saved_capture':
        from .wizard_movement_capture import validate_export_name
        try:
            validate_export_name(result['export_name'])
        except ValueError as error:
            raise WizardError('INVALID_EXPORT_NAME', str(error)) from error
    actor = PORTABLE_SETUP_ACTORS.get(action.action_id)
    if (
        action.action_id == "inspect_physical_passive_history"
        and re.fullmatch(r"operation-[a-f0-9]{32}", result["attempt_id"]) is None
    ):
        raise WizardError(
            "INVALID_ATTEMPT",
            "Use the exact saved operation ID; paths are not accepted.",
        )
    if (
        action.action_id == "inspect_passive_arm_history"
        and re.fullmatch(r"wizard-[a-f0-9]{32}", result["session_id"]) is None
    ):
        raise WizardError(
            "INVALID_SESSION",
            "Use the exact wizard- session ID from the saved report; paths are not accepted.",
        )
    if actor is not None and not portable_setup_operator_valid(result[actor]):
        # Reject before a ticket/queue/log is created, not minutes into setup.
        # The executor calls this same rule; its accepted ID format is unchanged.
        raise WizardError("INVALID_TEXT", PORTABLE_SETUP_OPERATOR_HELP)
    if action.action_id in {
        "physical_camera_mode_enter",
        "physical_camera_probe_prepare",
        "physical_camera_probe_review",
        "physical_camera_probe",
        "physical_camera_configuration_capture",
    }:
        from .physical_camera_mode_entry import camera_mode_operator_valid

        # Reject malformed entry labels at preview, before queue consumption or
        # intent logging. The original entry codec and Setup use this same rule.
        if not camera_mode_operator_valid(result["operator_id"]):
            raise WizardError(
                "INVALID_TEXT",
                "Use a trimmed setup label of 1–64 UTF-8 bytes, without control characters.",
            )
    return result
