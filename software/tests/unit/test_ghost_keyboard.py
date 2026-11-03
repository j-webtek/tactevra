import json
import hashlib
import importlib.util
import math
from pathlib import Path
import pytest
from rocell.application import ghost_keyboard as ghost
from rocell.application.wizard_worker import run
from test_arrival_wizard_service import make_service, _run
from test_movement_campaign_ui import render

ROOT=Path(__file__).resolve().parents[3]


def _load_key_mechanics():
    path=ROOT/'software/integrations/isaac_sim/representative_key_mechanics.py'
    spec=importlib.util.spec_from_file_location('representative_key_mechanics',path)
    module=importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('text',['a','aba','abc','cba','aaaaaaaa'])
def test_nominal_route_preserves_repetitions_and_retracts(text):
    r=ghost.rehearse_ghost_keyboard(ROOT,text)
    assert r['status']=='SAMPLED_GHOST_ROUTE_PASS'
    assert r['requested_keys']==list(text.upper())
    assert len(r['legs'])==len(text)*4
    for i,leg in enumerate(r['legs']):
        assert leg['phase']==('travel','hover','virtual_downstroke','retract')[i%4]
        assert all(s['accepted'] for s in leg['samples'])
        if leg['phase']=='travel':
            assert leg['start'][2]==leg['target'][2]==230
        if i: assert leg['start']==r['legs'][i-1]['target']
    assert r['legs'][-1]['target'][2]==230
    assert not r['camera_required'] and not r['hardware_access']
    assert not r['motion_authorized'] and not r['full_arm_clearance_verified']
    assert r['report_sha256']==ghost.rehearse_ghost_keyboard(ROOT,text)['report_sha256']


def test_transform_is_explicit_and_not_board_registration():
    r=ghost.rehearse_ghost_keyboard(ROOT,'b')
    assert r['legs'][0]['target']==[340,19,230,0]
    assert r['layout']['transform_basis']=='NOMINAL_SIMULATION_ONLY'
    assert not r['layout']['installed_tool_offset_applied']


@pytest.mark.parametrize('text',['','abcdef','A','a'*9,None])
def test_invalid_sequences_rejected(text):
    with pytest.raises(ValueError): ghost.rehearse_ghost_keyboard(ROOT,text)


def test_ik_failure_stops_preview(monkeypatch):
    def fail(*args): raise ValueError('unreachable')
    monkeypatch.setattr(ghost,'inverse',fail)
    r=ghost.rehearse_ghost_keyboard(ROOT,'abc')
    assert r['status']=='GHOST_ROUTE_REJECTED'
    assert len(r['legs'])==1 and len(r['legs'][0]['samples'])==1
    assert r['first_failure']['reason']=='IK_DOMAIN'


def test_unreviewed_layout_change_rejected(tmp_path):
    p=tmp_path/'software/config/ghost_keyboard_v1.json'
    p.parent.mkdir(parents=True)
    d=json.loads((ROOT/'software/config/ghost_keyboard_v1.json').read_bytes())
    d['origin_controller_mm'][2]=0
    p.write_text(json.dumps(d))
    with pytest.raises(ValueError): ghost.rehearse_ghost_keyboard(tmp_path)


@pytest.mark.parametrize('mode',['physical','rehearsal'])
def test_wizard_and_export_are_camera_free(make_service,mode):
    service,runner,_=make_service(mode=mode)
    runner.run=lambda action,values,**kw:run(ROOT,action,values,kw['cell_id'])
    op=_run(service,'rehearse_ghost_keyboard',{'text':'aba'})
    assert op['status']=='SUCCEEDED'
    assert op['result']['device_open_count']==0
    assert op['result']['motion_command_count']==0
    assert 'SAMPLED_GHOST_ROUTE_PASS' in render(op)
    export=_run(service,'export_logs')
    assert export['status']=='SUCCEEDED'
    path=Path(export['result']['receipt']['path'])/f"attachment-result-{op['operation_id'].removeprefix('operation-')}.json"
    assert json.loads(path.read_bytes())==op['result']


def test_representative_key_mechanics_derive_reviewed_layout_and_zero_authority():
    mechanics=_load_key_mechanics()
    profile=mechanics.build_profile(ROOT/'software/config/nominal_target_profiles.json')
    assert profile['representative_keys']==['H','1','SPACE','ENTER','PERIOD']
    assert profile['regions']['H']['center_board_xy_mm']==pytest.approx([216.55,154.0])
    assert profile['regions']['1']['center_board_xy_mm']==pytest.approx([107.0,196.0])
    assert profile['regions']['SPACE']['center_board_xy_mm']==pytest.approx([224.0,112.0])
    assert profile['status']=='PROVISIONAL_SIMULATION_ONLY'
    assert profile['provenance']['state']=='SYNTHETIC_BOUNDED_PRIOR_NOT_PRODUCT_SPECIFICATION'
    assert not any(profile['authority'].values())
    assert profile==mechanics.build_profile(ROOT/'software/config/nominal_target_profiles.json')


def test_fixed_base_rotation_and_root_invariant_helpers():
    mechanics=_load_key_mechanics()
    canonical=mechanics.canonical_active_rotation_row_major_from_gf_rows([
        [0.0,1.0,0.0],
        [-1.0,0.0,0.0],
        [0.0,0.0,1.0],
    ])
    assert canonical==[
        0.0,-1.0,0.0,
        1.0,0.0,0.0,
        0.0,0.0,1.0,
    ]

    passed=mechanics.evaluate_root_pose_invariant(
        [0.385,0.532,0.0701],
        [1.0,0.0,0.0,0.0],
        [0.38501,0.532,0.0701],
        [-1.0,0.0,0.0,0.0],
        translation_tolerance_mm=0.05,
        orientation_tolerance_deg=0.01,
    )
    assert passed['passed'] is True
    assert passed['translation_delta_mm']==pytest.approx(0.01)

    failed=mechanics.evaluate_root_pose_invariant(
        [0.0,0.0,0.0],
        [1.0,0.0,0.0,0.0],
        [0.0,0.0,-0.001],
        [1.0,0.0,0.0,0.0],
        translation_tolerance_mm=0.05,
        orientation_tolerance_deg=0.01,
    )
    assert failed['passed'] is False


def test_representative_key_mechanics_campaign_distinguishes_failure_classes():
    mechanics=_load_key_mechanics()
    receipt=mechanics.run_contract_campaign(ROOT/'software/config/nominal_target_profiles.json')
    assert receipt['status']=='PASS'
    assert receipt['case_count']==11
    assert receipt['passed_case_count']==11
    results={case['name']:case['result'] for case in receipt['cases']}
    for key in ('h','1','space','enter','period'):
        assert results[f'nominal_{key}']['disposition']=='ACCEPTED'
    assert {results[name]['disposition'] for name in (
        'shallow_h','off_center_h','excessive_h','double_h',
        'incomplete_release_h','neighbor_h_j',
    )}=={
        'SHALLOW_PRESS','OFF_CENTER_PRESS','EXCESSIVE_TRAVEL',
        'DOUBLE_ACTIVATION','INCOMPLETE_RELEASE','NEIGHBORING_KEY_CONTACT',
    }
    assert not receipt['authority']['hardware']
    assert receipt==mechanics.run_contract_campaign(ROOT/'software/config/nominal_target_profiles.json')


def test_representative_key_activation_is_geometry_derived_not_caller_named():
    mechanics=_load_key_mechanics()
    profile=mechanics.build_profile(ROOT/'software/config/nominal_target_profiles.json')
    center=profile['regions']['1']['center_board_xy_mm']
    result=mechanics.evaluate_trace(profile,[
        {'time_s':0.00,'tip_x_board_mm':center[0],'tip_y_board_mm':center[1],'compression_mm':0.0},
        {'time_s':0.02,'tip_x_board_mm':center[0],'tip_y_board_mm':center[1],'compression_mm':2.2},
        {'time_s':0.04,'tip_x_board_mm':center[0],'tip_y_board_mm':center[1],'compression_mm':0.0},
    ])
    assert result['accepted']
    assert result['resolved_key']=='1'
    assert result['activation_count']==1


def test_representative_key_mechanics_reject_tampered_layout_and_profile(tmp_path):
    mechanics=_load_key_mechanics()
    source=ROOT/'software/config/nominal_target_profiles.json'
    data=json.loads(source.read_bytes())
    data['status']='MEASURED'
    path=tmp_path/'nominal_target_profiles.json'
    path.write_text(json.dumps(data))
    with pytest.raises(mechanics.MechanicsContractError,match='status changed'):
        mechanics.build_profile(path)

    profile=mechanics.build_profile(source)
    profile['mechanics_prior']['activation_mm']['nominal']=99.0
    center=profile['regions']['H']['center_board_xy_mm']
    with pytest.raises(mechanics.MechanicsContractError,match='hash mismatch'):
        mechanics.evaluate_trace(profile,[
            {'time_s':0.0,'tip_x_board_mm':center[0],'tip_y_board_mm':center[1],'compression_mm':0.0},
            {'time_s':0.1,'tip_x_board_mm':center[0],'tip_y_board_mm':center[1],'compression_mm':0.0},
        ])


def test_native_h_tip_trajectory_is_smooth_bounded_and_retracts():
    mechanics=_load_key_mechanics()
    rows=mechanics.build_native_tip_trajectory(rest_top_z_m=0.021,tip_radius_m=0.001,dt=1/120)
    assert len(rows)==600
    assert [row['step'] for row in rows]==list(range(600))
    assert rows[0]['tip_z_m']==pytest.approx(0.024)
    assert rows[-1]['tip_z_m']==pytest.approx(0.024)
    assert min(row['tip_z_m'] for row in rows)==pytest.approx(0.0193)
    assert max(abs(rows[i+1]['tip_z_m']-rows[i]['tip_z_m']) for i in range(599))<0.00005


def test_native_h_displacement_is_assessed_by_shared_contract():
    mechanics=_load_key_mechanics()
    profile=mechanics.build_profile(ROOT/'software/config/nominal_target_profiles.json')
    compressions=[0.0,1.0,2.2,3.0,1.2,0.0]
    rows=[{
        'time_s':index*0.02,
        'key_center_z_m':0.018-compression/1000,
        'tip_key_separation_m':-0.0001 if compression else 0.001,
    } for index,compression in enumerate(compressions)]
    rows[0]['key_center_z_m']=0.0179
    result=mechanics.assess_native_key_trace(profile,rows,rest_key_z_m=0.018)
    assert result['accepted']
    assert result['resolved_key']=='H'
    assert result['native_contact_observed']
    assert result['native_contact_step_count']==4


def test_robot_tcp_binding_rejects_surface_only_endpoint_and_derives_overtravel():
    mechanics=_load_key_mechanics()
    profile=mechanics.build_profile(ROOT/'software/config/nominal_target_profiles.json')
    bundle=json.loads((
        ROOT/'software/integrations/isaac_sim/evidence/'
        'actual_emitter_joint_schedule_bundle_9e5c878_20260929.json'
    ).read_bytes())
    result=mechanics.bind_robot_tcp_contact_requirement(profile,bundle)
    assert result['status']=='BLOCKED_CONTACT_ENDPOINT_REQUIRES_OVERTRAVEL'
    assert result['source_contact_endpoint_count']==2
    assert result['source_contact_target_board_mm']==pytest.approx([216.55,154.0,21.0])
    assert result['source_scheduled_compression_mm']==pytest.approx(0.0)
    assert result['required_press_depth_mm']==pytest.approx(2.7)
    assert result['required_contact_target_board_mm']==pytest.approx([216.55,154.0,18.3])
    assert result['joint_schedule_regeneration_required'] is True
    assert result['ik_qualification_required'] is True
    assert result['native_replay_required'] is True
    assert result['authority']=={
        'hardware':False,'motion':False,'physical_keyboard_qualification':False,
    }
    assert result['hardware_writes']==0
    assert result['physical_movements']==0


def test_robot_tcp_binding_accepts_mechanics_compatible_endpoint():
    mechanics=_load_key_mechanics()
    profile=mechanics.build_profile(ROOT/'software/config/nominal_target_profiles.json')
    source=json.loads((
        ROOT/'software/integrations/isaac_sim/evidence/'
        'actual_emitter_joint_schedule_bundle_9e5c878_20260929.json'
    ).read_bytes())
    bundle=json.loads(json.dumps(source))
    for sample in bundle['samples']:
        if sample.get('target_id')=='H' and sample.get('phase')=='CONTACT' and sample.get('phase_endpoint') is True:
            sample['expected_tool_tip_board_mm'][2]=18.3
    unsigned={key:value for key,value in bundle.items() if key!='bundle_sha256'}
    bundle['bundle_sha256']=mechanics._canonical_sha256(unsigned)
    result=mechanics.bind_robot_tcp_contact_requirement(profile,bundle)
    assert result['status']=='READY_FOR_DRIVE_CONTROLLED_NATIVE_REPLAY'
    assert result['source_scheduled_compression_mm']==pytest.approx(2.7)
    assert result['joint_schedule_regeneration_required'] is False


def test_robot_tcp_binding_fails_closed_on_authority_or_hash_tamper():
    mechanics=_load_key_mechanics()
    profile=mechanics.build_profile(ROOT/'software/config/nominal_target_profiles.json')
    source=json.loads((
        ROOT/'software/integrations/isaac_sim/evidence/'
        'actual_emitter_joint_schedule_bundle_9e5c878_20260929.json'
    ).read_bytes())
    hash_tampered=json.loads(json.dumps(source))
    hash_tampered['samples'][0]['phase']='CONTACT'
    with pytest.raises(mechanics.MechanicsContractError,match='hash mismatch'):
        mechanics.bind_robot_tcp_contact_requirement(profile,hash_tampered)

    source['physical_authority']=True
    unsigned={key:value for key,value in source.items() if key!='bundle_sha256'}
    source['bundle_sha256']=mechanics._canonical_sha256(unsigned)
    with pytest.raises(mechanics.MechanicsContractError,match='zero-authority'):
        mechanics.bind_robot_tcp_contact_requirement(profile,source)


def test_robot_tcp_cartesian_regeneration_replaces_only_h_contact_endpoints():
    mechanics=_load_key_mechanics()
    profile=mechanics.build_profile(ROOT/'software/config/nominal_target_profiles.json')
    bundle=json.loads((
        ROOT/'software/integrations/isaac_sim/evidence/'
        'actual_emitter_joint_schedule_bundle_9e5c878_20260929.json'
    ).read_bytes())
    result=mechanics.build_robot_tcp_cartesian_schedule_request(profile,bundle)
    assert result['status']=='READY_FOR_IK_QUALIFICATION'
    assert result['sample_count']==len(bundle['samples'])==133
    assert len(result['modified_contact_sequences'])==2
    assert result['required_contact_target_board_mm']==pytest.approx([216.55,154.0,18.3])
    assert result['joint_positions_included'] is False
    assert result['source_joint_positions_reused'] is False
    assert result['ik_qualification_required'] is True
    assert result['collision_qualification_required'] is True
    assert result['native_replay_required'] is True
    modified=set(result['modified_contact_sequences'])
    for source,regenerated in zip(bundle['samples'],result['samples']):
        assert regenerated['sequence']==source['sequence']
        assert regenerated['time_from_start_ns']==source['time_from_start_ns']
        assert regenerated['phase']==source['phase']
        assert regenerated['target_id']==source['target_id']
        assert 'joint_positions_rad' not in regenerated
        if source['sequence'] in modified:
            assert regenerated['expected_tool_tip_board_mm']==pytest.approx([216.55,154.0,18.3])
        else:
            assert regenerated['expected_tool_tip_board_mm']==source['expected_tool_tip_board_mm']
    assert [
        row['target_id'] for row in result['samples']
        if row['phase']=='CONTACT' and row['phase_endpoint'] is True
    ]==bundle['ordered_target_ids']
    unsigned={key:value for key,value in result.items() if key!='request_sha256'}
    assert result['request_sha256']==mechanics._canonical_sha256(unsigned)


def test_robot_tcp_cartesian_regeneration_rejects_noncontiguous_source():
    mechanics=_load_key_mechanics()
    profile=mechanics.build_profile(ROOT/'software/config/nominal_target_profiles.json')
    bundle=json.loads((
        ROOT/'software/integrations/isaac_sim/evidence/'
        'actual_emitter_joint_schedule_bundle_9e5c878_20260929.json'
    ).read_bytes())
    bundle['samples'][2]['sequence']=99
    unsigned={key:value for key,value in bundle.items() if key!='bundle_sha256'}
    bundle['bundle_sha256']=mechanics._canonical_sha256(unsigned)
    with pytest.raises(mechanics.MechanicsContractError,match='not contiguous'):
        mechanics.build_robot_tcp_cartesian_schedule_request(profile,bundle)


def test_robot_tcp_cartesian_schedule_passes_canonical_ik_screen():
    mechanics=_load_key_mechanics()
    profile=mechanics.build_profile(ROOT/'software/config/nominal_target_profiles.json')
    bundle=json.loads((
        ROOT/'software/integrations/isaac_sim/evidence/'
        'actual_emitter_joint_schedule_bundle_9e5c878_20260929.json'
    ).read_bytes())
    request=mechanics.build_robot_tcp_cartesian_schedule_request(profile,bundle)
    result=mechanics.screen_robot_tcp_cartesian_schedule_ik(
        request,bundle,profile,workspace=ROOT,
    )
    assert result['status']=='READY_FOR_COLLISION_QUALIFICATION'
    assert result['sample_count']==result['evaluated_sample_count']==133
    assert result['ik_all_samples_accepted'] is True
    assert [
        row['waypoint_sequence'] for row in result['modified_contact_results']
    ]==[35,38]
    for row in result['modified_contact_results']:
        assert row['accepted'] is True
        assert row['position_error_mm']<0.001
        assert row['minimum_normalized_arm_joint_margin']>0.15
        assert row['maximum_joint_delta_rad']<0.04
    assert result['collision_screening_executed'] is False
    assert result['continuous_collision_proven'] is False
    assert result['hardware_access'] is False
    assert result['physical_authority'] is False
    assert result['hardware_writes']==result['physical_movements']==0
    unsigned={key:value for key,value in result.items() if key!='receipt_sha256'}
    assert result['receipt_sha256']==mechanics._canonical_sha256(unsigned)


def test_placement_tcp_control_reproduces_profile_ik_and_propagates_matrix():
    mechanics=_load_key_mechanics()
    profile=mechanics.build_profile(ROOT/'software/config/nominal_target_profiles.json')
    bundle=json.loads((
        ROOT/'software/integrations/isaac_sim/evidence/'
        'actual_emitter_joint_schedule_bundle_9e5c878_20260929.json'
    ).read_bytes())
    request=mechanics.build_robot_tcp_cartesian_schedule_request(profile,bundle)
    baseline=mechanics.screen_robot_tcp_cartesian_schedule_ik(
        request,bundle,profile,workspace=ROOT,
    )
    virtual=json.loads(
        (ROOT/'software/config/virtual_commissioning_profile.json').read_bytes()
    )
    placement=virtual['study_input']['physical_placement_input']
    candidate={
        'candidate_id':'placement-tcp-control-test',
        'candidate_classification':'RETAINED_ARM198_CONTROL',
        'keyboard_tcp_length_mm':virtual['study_input']['route_tool_lengths_mm'][
            'keyboard'
        ],
        'robot_placement_matrix_row_major':placement['matrix_row_major'],
    }
    screened=mechanics.screen_robot_tcp_cartesian_schedule_ik(
        request,bundle,profile,workspace=ROOT,placement_tcp_candidate=candidate,
    )
    assert screened['joint_results']==baseline['joint_results']
    assert screened['metrics']['maximum_position_error_mm']==pytest.approx(
        baseline['metrics']['maximum_position_error_mm']
    )
    assert screened['metrics']['minimum_normalized_arm_joint_margin']==pytest.approx(
        baseline['metrics']['minimum_normalized_arm_joint_margin']
    )
    assert screened['placement_tcp_candidate_id']==candidate['candidate_id']
    assert screened['robot_placement_matrix_row_major']==placement['matrix_row_major']

    collision_candidate={
        'schema':'tactevra.simulation_collision_candidate.v1',
        'scope':'SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY',
        'status':'EXPLORATORY_UNINSTALLED_COLLISION_CANDIDATE_FAMILY',
        'installed':False,'installed_profile_eligible':False,
        'robot_bodies':[{'body_id':'robot:base_link'}],
        'workcell_bodies':[{'body_id':'workcell:keyboard'}],
        'blockers':['EXPLORATORY_GEOMETRY_UNINSTALLED'],
        'simulation_diagnostic_ready':False,
        'hardware_write_count':0,'physical_movement_count':0,
        'commands':[],'physical_authority':False,
    }
    collision_candidate['candidate_sha256']=mechanics._canonical_sha256(
        collision_candidate
    )
    lock=json.loads((ROOT/'software/config/isaac_sim_toolchain_lock.json').read_bytes())
    replay=mechanics.build_robot_tcp_collision_replay_request(
        screened,collision_candidate,lock
    )
    assert replay['placement_tcp_candidate_id']==candidate['candidate_id']
    assert replay['robot_placement_matrix_row_major']==placement['matrix_row_major']


def test_robot_tcp_cartesian_ik_screen_rejects_request_hash_tamper():
    mechanics=_load_key_mechanics()
    profile=mechanics.build_profile(ROOT/'software/config/nominal_target_profiles.json')
    bundle=json.loads((
        ROOT/'software/integrations/isaac_sim/evidence/'
        'actual_emitter_joint_schedule_bundle_9e5c878_20260929.json'
    ).read_bytes())
    request=mechanics.build_robot_tcp_cartesian_schedule_request(profile,bundle)
    request['samples'][35]['expected_tool_tip_board_mm'][2]=18.2
    with pytest.raises(mechanics.MechanicsContractError,match='request hash mismatch'):
        mechanics.screen_robot_tcp_cartesian_schedule_ik(
            request,bundle,profile,workspace=ROOT,
        )

    request=mechanics.build_robot_tcp_cartesian_schedule_request(profile,bundle)
    request['required_contact_target_board_mm'][2]=18.2
    for sequence in request['modified_contact_sequences']:
        request['samples'][sequence]['expected_tool_tip_board_mm'][2]=18.2
    unsigned={key:value for key,value in request.items() if key!='request_sha256'}
    request['request_sha256']=mechanics._canonical_sha256(unsigned)
    with pytest.raises(mechanics.MechanicsContractError,match='governed mechanics'):
        mechanics.screen_robot_tcp_cartesian_schedule_ik(
            request,bundle,profile,workspace=ROOT,
        )


def test_route_variant_ik_admission_rejects_resealed_plan_divergence():
    mechanics=_load_key_mechanics()
    profile=mechanics.build_profile(ROOT/'software/config/nominal_target_profiles.json')
    bundle=json.loads((
        ROOT/'software/integrations/isaac_sim/evidence/'
        'actual_emitter_joint_schedule_bundle_9e5c878_20260929.json'
    ).read_bytes())
    source=mechanics.build_robot_tcp_cartesian_schedule_request(profile,bundle)
    sequence=next(
        sample['sequence'] for sample in source['samples']
        if sample['phase']=='TRANSIT' and sample['phase_endpoint'] is False
        and sample['expected_tool_tip_board_mm'][2]!=70.0
    )
    plan={
        'schema':mechanics.PHYSICAL_BLOCKER_EXPERIMENT_PLAN_SCHEMA,
        'status':'READY_FOR_ZERO_AUTHORITY_VARIANT_GENERATION',
        'source_cartesian_request_sha256':source['request_sha256'],
        'physical_workcell_top_z_mm':21.0,'proposed_transit_z_mm':70.0,
        'transit_lift_cartesian_sequences':[sequence],
        'route_variant_applied':False,'collision_geometry_changed':False,
        'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
    }
    plan['plan_sha256']=mechanics._canonical_sha256(plan)
    variant=mechanics.build_physical_blocker_route_variant(source,plan)
    variant['samples'][sequence]['expected_tool_tip_board_mm'][0]+=1.0
    unsigned={key:value for key,value in variant.items() if key!='request_sha256'}
    variant['request_sha256']=mechanics._canonical_sha256(unsigned)
    with pytest.raises(mechanics.MechanicsContractError,match='governed mechanics'):
        mechanics.screen_robot_tcp_cartesian_schedule_ik(
            variant,bundle,profile,workspace=ROOT,
            experiment_plan=plan,source_cartesian_request=source,
        )


def test_robot_tcp_collision_request_binds_exact_ik_and_bounded_samples():
    mechanics=_load_key_mechanics()
    profile=mechanics.build_profile(ROOT/'software/config/nominal_target_profiles.json')
    bundle=json.loads((
        ROOT/'software/integrations/isaac_sim/evidence/'
        'actual_emitter_joint_schedule_bundle_9e5c878_20260929.json'
    ).read_bytes())
    cartesian=mechanics.build_robot_tcp_cartesian_schedule_request(profile,bundle)
    ik=mechanics.screen_robot_tcp_cartesian_schedule_ik(
        cartesian,bundle,profile,workspace=ROOT,
    )
    candidate={
        'schema':'tactevra.simulation_collision_candidate.v1',
        'scope':'SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY',
        'status':'EXPLORATORY_UNINSTALLED_COLLISION_CANDIDATE_FAMILY',
        'installed':False,
        'installed_profile_eligible':False,
        'robot_bodies':[{'body_id':'robot:base_link'}],
        'workcell_bodies':[{'body_id':'workcell:keyboard'}],
        'blockers':['MOVING_CABLE_GEOMETRY_UNMEASURED'],
        'simulation_diagnostic_ready':False,
        'hardware_write_count':0,
        'physical_movement_count':0,
        'commands':[],
        'physical_authority':False,
    }
    candidate['candidate_sha256']=mechanics._canonical_sha256(candidate)
    lock=json.loads((ROOT/'software/config/isaac_sim_toolchain_lock.json').read_bytes())
    result=mechanics.build_robot_tcp_collision_replay_request(ik,candidate,lock)
    assert result['status']=='READY_FOR_ZERO_AUTHORITY_COLLISION_DIAGNOSTIC'
    assert result['source_ik_receipt_sha256']==ik['receipt_sha256']
    assert result['source_joint_result_count']==133
    assert 133 <= result['bounded_sample_count'] <= 256
    assert result['bounded_samples'][0]['sample_sequence']==0
    assert result['bounded_samples'][-1]['source_segment_index']==132
    assert max(
        max(
            abs(later['joint_positions_rad'][name]-earlier['joint_positions_rad'][name])
            for name in result['joint_order']
        )
        for earlier,later in zip(result['bounded_samples'],result['bounded_samples'][1:])
    ) <= 0.05 + 1e-12
    assert result['diagnostic_only'] is True
    assert result['installed_collision_qualified'] is False
    assert result['native_contact_replay_authorized'] is False
    assert result['hardware_access'] is result['physical_authority'] is False
    assert result['controller_commands']==[]
    unsigned={key:value for key,value in result.items() if key!='request_sha256'}
    assert result['request_sha256']==mechanics._canonical_sha256(unsigned)

    candidate['blockers'].append('TAMPER')
    with pytest.raises(mechanics.MechanicsContractError,match='candidate hash mismatch'):
        mechanics.build_robot_tcp_collision_replay_request(ik,candidate,lock)


def test_robot_tcp_collision_diagnostic_admission_binds_native_inputs():
    mechanics=_load_key_mechanics()
    profile=mechanics.build_profile(ROOT/'software/config/nominal_target_profiles.json')
    bundle=json.loads((
        ROOT/'software/integrations/isaac_sim/evidence/'
        'actual_emitter_joint_schedule_bundle_9e5c878_20260929.json'
    ).read_bytes())
    cartesian=mechanics.build_robot_tcp_cartesian_schedule_request(profile,bundle)
    ik=mechanics.screen_robot_tcp_cartesian_schedule_ik(
        cartesian,bundle,profile,workspace=ROOT,
    )
    box={
        'kind':'oriented_box','center_mm':[0.0,0.0,0.0],
        'half_extents_mm':[1.0,2.0,3.0],
        'rotation_row_major':[0.0,-1.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0],
    }
    candidate={
        'schema':'tactevra.simulation_collision_candidate.v1',
        'scope':'SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY',
        'status':'EXPLORATORY_UNINSTALLED_COLLISION_CANDIDATE_FAMILY',
        'installed':False,'installed_profile_eligible':False,
        'robot_bodies':[
            {'body_id':'robot:base_link','parent_frame':'base_link','primitives':[box]},
        ],
        'workcell_bodies':[
            {'body_id':'workcell:keyboard','parent_frame':'board','primitives':[box]},
        ],
        'blockers':['MOVING_CABLE_GEOMETRY_UNMEASURED'],
        'simulation_diagnostic_ready':False,
        'hardware_write_count':0,'physical_movement_count':0,
        'commands':[],'physical_authority':False,
    }
    candidate['candidate_sha256']=mechanics._canonical_sha256(candidate)
    lock=json.loads((ROOT/'software/config/isaac_sim_toolchain_lock.json').read_bytes())
    request=mechanics.build_robot_tcp_collision_replay_request(ik,candidate,lock)
    virtual_bytes=(ROOT/'software/config/virtual_commissioning_profile.json').read_bytes()
    usd_bytes=b'synthetic governed USD bytes'
    import_receipt={
        'schema':'tactevra.isaac_sim_urdf_import.v1',
        'external_files':[{
            'path':'robot.usda','sha256':hashlib.sha256(usd_bytes).hexdigest(),
            'size_bytes':len(usd_bytes),
        }],
        'articulation_root_normalization':{
            'expected_live_dof_order':request['joint_order']+['link5_to_gripper_link'],
        },
        'hardware_access':False,'physical_authority':False,
        'wire_commands':[],'hardware_writes':0,'physical_movements':0,
    }
    import_receipt['receipt_sha256']=mechanics._canonical_sha256(import_receipt)
    admission=mechanics.admit_robot_tcp_collision_diagnostic(
        request,ik,candidate,virtual_bytes,usd_bytes,import_receipt,
    )
    assert admission['status']=='READY_TO_START_SELECTED_ISAAC_COLLISION_DIAGNOSTIC'
    assert admission['bounded_sample_count']==request['bounded_sample_count']
    assert admission['request_sha256']==request['request_sha256']
    assert admission['collision_candidate_sha256']==candidate['candidate_sha256']
    assert admission['robot_body_count']==admission['workcell_body_count']==1
    assert admission['hardware_access'] is admission['physical_authority'] is False
    assert admission['controller_commands']==[] and admission['gate_promotions']==[]
    unsigned={key:value for key,value in admission.items() if key!='admission_sha256'}
    assert admission['admission_sha256']==mechanics._canonical_sha256(unsigned)

    reflected=json.loads(json.dumps(candidate))
    reflected['robot_bodies'][0]['primitives'][0]['rotation_row_major']=[
        1.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,-1.0,
    ]
    reflected.pop('candidate_sha256')
    reflected['candidate_sha256']=mechanics._canonical_sha256(reflected)
    reflected_request=mechanics.build_robot_tcp_collision_replay_request(
        ik,reflected,lock,
    )
    with pytest.raises(mechanics.MechanicsContractError,match='right-handed'):
        mechanics.admit_robot_tcp_collision_diagnostic(
            reflected_request,ik,reflected,virtual_bytes,usd_bytes,import_receipt,
        )

    request['bounded_samples'][0]['joint_positions_rad'][request['joint_order'][0]]+=0.1
    with pytest.raises(mechanics.MechanicsContractError,match='request hash mismatch'):
        mechanics.admit_robot_tcp_collision_diagnostic(
            request,ik,candidate,virtual_bytes,usd_bytes,import_receipt,
        )


def test_collision_pair_policy_proposal_is_classified_but_unapplied():
    mechanics=_load_key_mechanics()
    robot_ids=['base_link','link1','link2','link3','link4','link5','gripper']
    candidate={
        'schema':'tactevra.simulation_collision_candidate.v1',
        'installed':False,'installed_profile_eligible':False,
        'robot_bodies':[{'body_id':f'robot:{name}'} for name in robot_ids],
        'workcell_bodies':[
            {'body_id':'workcell:keyboard'},
            {'body_id':'workcell:station:keyboard_left'},
        ],
        'blockers':['MOVING_CABLE_GEOMETRY_UNMEASURED'],
        'hardware_write_count':0,'physical_movement_count':0,
        'commands':[],'physical_authority':False,
    }
    candidate['candidate_sha256']=mechanics._canonical_sha256(candidate)
    pairs=[
        ('robot:base_link','robot:link1',149),
        ('robot:link1','robot:link2',149),
        ('robot:link2','robot:link3',149),
        ('robot:link3','robot:link4',149),
        ('robot:gripper','robot:link5',149),
        ('robot:link5','workcell:keyboard',20),
        ('robot:link4','workcell:station:keyboard_left',21),
    ]
    receipt={
        'schema':'tactevra.isaac_lm1_robot_tcp_collision_diagnostic.v1',
        'status':'DIAGNOSTIC_OVERLAPS_OBSERVED',
        'source_bindings':{
            'collision_candidate_sha256':candidate['candidate_sha256'],
        },
        'bounded_sample_count':149,
        'unique_collision_pair_count':len(pairs),
        'pair_observations':[
            {
                'body_pair':list(pair[:2]),'sample_count':pair[2],
                'persistent_across_all_samples':pair[2]==149,
            }
            for pair in pairs
        ],
        'collision_screening_executed':True,
        'installed_collision_qualified':False,
        'continuous_collision_proven':False,
        'gate_promotions':[],
    }
    receipt['receipt_sha256']=mechanics._canonical_sha256(receipt)
    proposal=mechanics.build_collision_pair_policy_proposal(receipt,candidate)
    assert proposal['status']=='REVIEW_REQUIRED_COLLISION_PAIR_POLICY'
    assert proposal['proposed_exclusion_count']==5
    assert proposal['policy_applied'] is False
    assert proposal['installed_profile_eligible'] is False
    assert proposal['installed_collision_qualified'] is False
    assert proposal['gate_promotions']==[]
    dispositions={
        tuple(row['body_pair']):row['proposed_disposition']
        for row in proposal['pair_classifications']
    }
    assert dispositions[('robot:link5','workcell:keyboard')]==(
        'PHYSICAL_SOLID_COLLISION_OBSERVATION'
    )
    assert dispositions[('robot:link4','workcell:station:keyboard_left')]==(
        'PLANNING_ENVELOPE_ROUTE_BLOCKER'
    )
    unsigned={key:value for key,value in proposal.items() if key!='proposal_sha256'}
    assert proposal['proposal_sha256']==mechanics._canonical_sha256(unsigned)

    policy=mechanics.accept_collision_pair_policy_proposal(proposal)
    assert policy['status']=='ACCEPTED_FOR_ZERO_AUTHORITY_DIAGNOSTIC_ONLY'
    assert policy['accepted_exclusion_count']==5
    assert policy['diagnostic_policy_active'] is True
    assert policy['installed_profile_active'] is False
    assert policy['physical_solid_pairs_excluded']==[]
    assert policy['planning_envelope_pairs_excluded']==[]
    assert policy['gate_promotions']==[]
    policy_unsigned={key:value for key,value in policy.items() if key!='policy_sha256'}
    assert policy['policy_sha256']==mechanics._canonical_sha256(policy_unsigned)

    request={
        'schema':'tactevra.isaac_lm1_robot_tcp_collision_replay_request.v1',
        'status':'READY_FOR_ZERO_AUTHORITY_COLLISION_DIAGNOSTIC',
        'collision_candidate_sha256':candidate['candidate_sha256'],
        'diagnostic_only':True,
        'installed_collision_qualified':False,
        'continuous_collision_proven':False,
        'native_contact_replay_authorized':False,
        'limitations':['exploratory_collision_candidate_is_uninstalled'],
        'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
    }
    request['request_sha256']=mechanics._canonical_sha256(request)
    bound=mechanics.bind_collision_pair_policy_request(request,policy)
    assert bound['schema']=='tactevra.isaac_lm1_robot_tcp_collision_replay_request.v2'
    assert bound['source_unfiltered_request_sha256']==request['request_sha256']
    assert bound['collision_pair_policy_sha256']==policy['policy_sha256']
    assert bound['collision_pair_policy_scope']=='DIAGNOSTIC_REPORTING_ONLY'
    assert bound['installed_collision_qualified'] is False
    bound_unsigned={key:value for key,value in bound.items() if key!='request_sha256'}
    assert bound['request_sha256']==mechanics._canonical_sha256(bound_unsigned)

    proposal_pair=receipt['pair_observations'][0]
    proposal_pair['sample_count']=150
    receipt['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in receipt.items() if key!='receipt_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='sample count'):
        mechanics.build_collision_pair_policy_proposal(receipt,candidate)


def test_station_route_predicate_separates_regions_from_physical_solids():
    mechanics=_load_key_mechanics()
    candidate={
        'schema':'tactevra.simulation_collision_candidate.v1',
        'installed':False,'installed_profile_eligible':False,
        'physical_authority':False,'hardware_write_count':0,
        'physical_movement_count':0,'commands':[],
        'workcell_bodies':[],
    }
    identity=[1.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,1.0]
    def body(body_id,center,half):
        return {
            'body_id':body_id,'parent_frame':'board','primitives':[{
                'kind':'oriented_box','center_mm':center,
                'half_extents_mm':half,'rotation_row_major':identity,
            }],
        }
    candidate['workcell_bodies']=[
        body('workcell:board_solid',[305.0,228.5,-9.0],[305.0,228.5,9.0]),
        body('workcell:keyboard',[242.5,158.5,10.5],[157.5,73.5,10.5]),
        body('workcell:phone',[538.15,166.4,7.95],[38.95,82.2,3.95]),
        body('workcell:station:keyboard_left',[172.25,168.0,17.5],[92.25,96.0,17.5]),
        body('workcell:station:keyboard_right',[323.75,168.0,17.5],[81.25,96.0,17.5]),
        body('workcell:station:phone_tcp',[504.15,166.4,17.5],[93.15,86.4,17.5]),
    ]
    candidate['candidate_sha256']=mechanics._canonical_sha256(candidate)
    samples=[
        {'sequence':0,'action_index':None,'phase':'PARK','target_id':None,
         'phase_endpoint':True,'expected_tool_tip_board_mm':[290.0,10.0,70.0]},
        {'sequence':1,'action_index':0,'phase':'TRANSIT','target_id':'H',
         'phase_endpoint':False,'expected_tool_tip_board_mm':[230.0,100.0,40.0]},
        {'sequence':2,'action_index':0,'phase':'HOVER','target_id':'H',
         'phase_endpoint':True,'expected_tool_tip_board_mm':[216.55,154.0,26.0]},
        {'sequence':3,'action_index':0,'phase':'CONTACT','target_id':'H',
         'phase_endpoint':True,'expected_tool_tip_board_mm':[216.55,154.0,18.3]},
        {'sequence':4,'action_index':1,'phase':'CONTACT','target_id':'PERIOD',
         'phase_endpoint':True,'expected_tool_tip_board_mm':[283.2,133.0,21.0]},
    ]
    request={
        'schema':mechanics.TCP_CARTESIAN_SCHEDULE_SCHEMA,
        'status':'READY_FOR_IK_QUALIFICATION','sample_count':len(samples),
        'samples':samples,'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
    }
    request['request_sha256']=mechanics._canonical_sha256(request)
    result=mechanics.build_station_route_predicate(
        request,candidate,{
            'H':['workcell:station:keyboard_left'],
            'PERIOD':['workcell:station:keyboard_right'],
        },
    )
    assert result['status']=='PASS'
    assert result['violation_count']==0
    assert result['physical_workcell_body_ids']==[
        'workcell:board_solid','workcell:keyboard','workcell:phone',
    ]
    assert result['physx_excluded_station_region_ids']==[
        'workcell:station:keyboard_left','workcell:station:keyboard_right',
        'workcell:station:phone_tcp',
    ]
    assert result['samples'][3]['occupied_station_regions']==[
        'workcell:station:keyboard_left'
    ]
    assert result['samples'][4]['occupied_station_regions']==[
        'workcell:station:keyboard_right'
    ]
    assert result['installed_profile_eligible'] is False
    assert result['hardware_access'] is result['physical_authority'] is False
    unsigned={key:value for key,value in result.items() if key!='predicate_sha256'}
    assert result['predicate_sha256']==mechanics._canonical_sha256(unsigned)

    rotated={
        'kind':'oriented_box','center_mm':[0.0,0.0,0.0],
        'half_extents_mm':[2.0,0.5,1.0],
        'rotation_row_major':[
            0.7071067811865476,-0.7071067811865476,0.0,
            0.7071067811865476,0.7071067811865476,0.0,
            0.0,0.0,1.0,
        ],
    }
    assert mechanics._point_inside_oriented_box(
        [1.0,1.0,0.0],rotated,label='rotated station'
    )
    assert not mechanics._point_inside_oriented_box(
        [1.0,-1.0,0.0],rotated,label='rotated station'
    )

    wrong=mechanics.build_station_route_predicate(
        request,candidate,{
            'H':['workcell:station:keyboard_right'],
            'PERIOD':['workcell:station:keyboard_right'],
        },
    )
    assert wrong['status']=='FAIL'
    assert wrong['violation_count']==1
    assert wrong['samples'][3]['violations']==[
        'CONTACT_OUTSIDE_BOUND_STATION_REGION',
    ]

    missing=dict(request)
    missing.pop('request_sha256')
    missing['request_sha256']=mechanics._canonical_sha256(missing)
    with pytest.raises(mechanics.MechanicsContractError,match='coverage differs'):
        mechanics.build_station_route_predicate(
            missing,candidate,{'H':['workcell:station:keyboard_left']},
        )


def test_physical_blocker_plan_separates_transit_and_endpoint_experiments():
    mechanics=_load_key_mechanics()
    identity=[1.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,1.0]
    def body(body_id,center,half):
        return {'body_id':body_id,'parent_frame':'board','primitives':[{
            'kind':'oriented_box','center_mm':center,'half_extents_mm':half,
            'rotation_row_major':identity,
        }]}
    candidate={
        'schema':'tactevra.simulation_collision_candidate.v1',
        'installed':False,'installed_profile_eligible':False,
        'physical_authority':False,'hardware_write_count':0,
        'physical_movement_count':0,'commands':[],
        'workcell_bodies':[
            body('workcell:board_solid',[305.0,228.5,-9.0],[305.0,228.5,9.0]),
            body('workcell:keyboard',[242.5,158.5,10.5],[157.5,73.5,10.5]),
            body('workcell:phone',[538.15,166.4,7.95],[38.95,82.2,3.95]),
            body('workcell:station:keyboard_left',[172.25,168.0,17.5],[92.25,96.0,17.5]),
        ],
    }
    candidate['candidate_sha256']=mechanics._canonical_sha256(candidate)
    request={
        'schema':mechanics.TCP_CARTESIAN_SCHEDULE_SCHEMA,
        'hardware_access':False,'controller_commands':[],
        'hardware_writes':0,'physical_movements':0,
    }
    request['request_sha256']=mechanics._canonical_sha256(request)
    profile={
        'status':'UNMEASURED_SENSITIVITY_OVERLAY',
        'study_input':{
            'study_input_id':'reach-test',
            'physical_placement_input':{'matrix_row_major':[
                1.0,0.0,0.0,385.0,0.0,1.0,0.0,532.0,
                0.0,0.0,1.0,70.1,0.0,0.0,0.0,1.0,
            ]},
        },
    }
    profile_sha256='a'*64
    receipt={
        'station_route_predicate_applied':True,
        'source_bindings':{
            'collision_candidate_sha256':candidate['candidate_sha256'],
            'virtual_profile_sha256':profile_sha256,
        },
        'hardware_access':False,'controller_commands':[],
        'hardware_writes':0,'physical_movements':0,
    }
    receipt['receipt_sha256']=mechanics._canonical_sha256(receipt)
    localization={
        'source_cartesian_request_sha256':request['request_sha256'],
        'source_diagnostic_receipt_sha256':receipt['receipt_sha256'],
        'physical_solid_blocker_pair_count':2,
        'planning_envelope_blocker_pair_count':0,
        'unreviewed_blocker_pair_count':0,
        'blocker_localizations':[
            {
                'body_pair':['robot:gripper','workcell:keyboard'],
                'sample_count':2,
                'samples':[
                    {'phase':'CONTACT','cartesian_sequence':3},
                    {'phase':'TRANSIT','cartesian_sequence':4},
                ],
            },
            {
                'body_pair':['robot:link2','workcell:board_solid'],
                'sample_count':1,
                'samples':[{'phase':'TRANSIT','cartesian_sequence':4}],
            },
        ],
        'hardware_access':False,'controller_commands':[],
        'hardware_writes':0,'physical_movements':0,
    }
    localization['proposal_sha256']=mechanics._canonical_sha256(localization)
    plan=mechanics.build_physical_blocker_experiment_plan(
        request,candidate,receipt,localization,profile,clearance_margin_mm=49.0,
        virtual_profile_sha256=profile_sha256,
    )
    assert plan['status']=='READY_FOR_ZERO_AUTHORITY_VARIANT_GENERATION'
    assert plan['physical_workcell_top_z_mm']==pytest.approx(21.0)
    assert plan['proposed_transit_z_mm']==pytest.approx(70.0)
    assert plan['transit_lift_cartesian_sequences']==[4]
    assert plan['endpoint_geometry_body_pairs']==[
        ['robot:gripper','workcell:keyboard']
    ]
    assert [item['experiment_class'] for item in plan['blocker_experiments']]==[
        'TRANSIT_LIFT_AND_ENDPOINT_GEOMETRY','TRANSIT_LIFT_ONLY',
    ]
    assert plan['route_variant_applied'] is False
    assert plan['collision_geometry_changed'] is False
    assert plan['hardware_access'] is plan['physical_authority'] is False
    unsigned={key:value for key,value in plan.items() if key!='plan_sha256'}
    assert plan['plan_sha256']==mechanics._canonical_sha256(unsigned)
    with pytest.raises(mechanics.MechanicsContractError,match='within'):
        mechanics.build_physical_blocker_experiment_plan(
            request,candidate,receipt,localization,profile,
            clearance_margin_mm=0.0,
            virtual_profile_sha256=profile_sha256,
        )


def test_physical_blocker_route_variant_changes_only_selected_transit_z():
    mechanics=_load_key_mechanics()
    samples=[
        {
            'sequence':0,'time_from_start_ns':0,'phase':'PARK',
            'phase_endpoint':True,'action_index':0,'target_id':None,
            'expected_tool_tip_board_mm':[290.0,10.0,70.0],
        },
        {
            'sequence':1,'time_from_start_ns':1,'phase':'TRANSIT',
            'phase_endpoint':False,'action_index':0,'target_id':'H',
            'expected_tool_tip_board_mm':[250.0,100.0,32.0],
        },
        {
            'sequence':2,'time_from_start_ns':2,'phase':'TRANSIT',
            'phase_endpoint':False,'action_index':0,'target_id':'H',
            'expected_tool_tip_board_mm':[240.0,120.0,28.0],
        },
        {
            'sequence':3,'time_from_start_ns':3,'phase':'CONTACT',
            'phase_endpoint':True,'action_index':0,'target_id':'H',
            'expected_tool_tip_board_mm':[230.0,130.0,16.0],
        },
    ]
    request={
        'schema':mechanics.TCP_CARTESIAN_SCHEDULE_SCHEMA,
        'status':'READY_FOR_IK_QUALIFICATION','source_bundle_sha256':'a'*64,
        'source_binding_sha256':'b'*64,'profile_sha256':'c'*64,'key_id':'H',
        'sample_count':len(samples),'total_time_ns':3,'ordered_target_ids':['H'],
        'modified_contact_sequences':[3],
        'required_contact_target_board_mm':[230.0,130.0,16.0],
        'samples':samples,'joint_positions_included':False,
        'source_joint_positions_reused':False,'ik_qualification_required':True,
        'collision_qualification_required':True,'native_replay_required':True,
        'authority':{'physical_motion':False},'hardware_access':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
        'limitations':['source limitation'],
    }
    request['request_sha256']=mechanics._canonical_sha256(request)
    plan={
        'schema':mechanics.PHYSICAL_BLOCKER_EXPERIMENT_PLAN_SCHEMA,
        'status':'READY_FOR_ZERO_AUTHORITY_VARIANT_GENERATION',
        'source_cartesian_request_sha256':request['request_sha256'],
        'physical_workcell_top_z_mm':21.0,'proposed_transit_z_mm':70.0,
        'transit_lift_cartesian_sequences':[1],
        'route_variant_applied':False,'collision_geometry_changed':False,
        'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
    }
    plan['plan_sha256']=mechanics._canonical_sha256(plan)

    variant=mechanics.build_physical_blocker_route_variant(request,plan)
    assert variant['source_cartesian_request_sha256']==request['request_sha256']
    assert variant['source_physical_blocker_experiment_plan_sha256']==plan['plan_sha256']
    assert variant['modified_transit_sequences']==[1]
    assert variant['samples'][1]['expected_tool_tip_board_mm']==[250.0,100.0,70.0]
    assert variant['samples'][0]==request['samples'][0]
    assert variant['samples'][2]==request['samples'][2]
    assert variant['samples'][3]==request['samples'][3]
    assert variant['route_variant_applied'] is True
    assert variant['collision_geometry_changed'] is False
    assert variant['installed_profile_eligible'] is False
    unsigned={key:value for key,value in variant.items() if key!='request_sha256'}
    assert variant['request_sha256']==mechanics._canonical_sha256(unsigned)

    invalid_plan=dict(plan)
    invalid_plan.pop('plan_sha256')
    invalid_plan['transit_lift_cartesian_sequences']=[3]
    invalid_plan['plan_sha256']=mechanics._canonical_sha256(invalid_plan)
    with pytest.raises(mechanics.MechanicsContractError,match='non-transit endpoint'):
        mechanics.build_physical_blocker_route_variant(request,invalid_plan)


def test_placement_tcp_search_plan_is_bounded_and_retains_control():
    mechanics=_load_key_mechanics()
    profile_sha256='a'*64
    collision_candidate_sha256='b'*64
    pair_policy_sha256='c'*64
    station_predicate_sha256='d'*64
    toolchain_sha256='e'*64
    plan={
        'schema':mechanics.PHYSICAL_BLOCKER_EXPERIMENT_PLAN_SCHEMA,
        'status':'READY_FOR_ZERO_AUTHORITY_VARIANT_GENERATION',
        'source_virtual_profile_sha256':profile_sha256,
        'source_collision_candidate_sha256':collision_candidate_sha256,
        'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
    }
    plan['plan_sha256']=mechanics._canonical_sha256(plan)
    route={
        'schema':mechanics.TCP_CARTESIAN_SCHEDULE_SCHEMA,
        'source_physical_blocker_experiment_plan_sha256':plan['plan_sha256'],
        'route_variant_applied':True,'collision_geometry_changed':False,
        'hardware_access':False,'controller_commands':[],
        'hardware_writes':0,'physical_movements':0,
    }
    route['request_sha256']=mechanics._canonical_sha256(route)
    receipt={
        'schema':mechanics.TCP_ROUTE_PREDICATE_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA,
        'status':'DIAGNOSTIC_BLOCKERS_OBSERVED',
        'station_route_predicate_applied':True,
        'collision_pair_policy_applied':True,
        'source_bindings':{
            'virtual_profile_sha256':profile_sha256,
            'collision_candidate_sha256':collision_candidate_sha256,
            'collision_pair_policy_sha256':pair_policy_sha256,
            'station_route_predicate_sha256':station_predicate_sha256,
            'toolchain_lock_sha256':toolchain_sha256,
        },
        'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
        'gate_promotions':[],
    }
    receipt['receipt_sha256']=mechanics._canonical_sha256(receipt)
    pairs=[
        ['robot:gripper','workcell:board_solid'],
        ['robot:gripper','workcell:keyboard'],
        ['robot:link2','workcell:board_solid'],
        ['robot:link3','workcell:board_solid'],
        ['robot:link4','workcell:board_solid'],
        ['robot:link5','workcell:board_solid'],
        ['robot:link5','workcell:keyboard'],
    ]
    localization={
        'schema':mechanics.TCP_COLLISION_BLOCKER_LOCALIZATION_SCHEMA,
        'source_cartesian_request_sha256':route['request_sha256'],
        'source_diagnostic_receipt_sha256':receipt['receipt_sha256'],
        'physical_solid_blocker_pair_count':7,
        'planning_envelope_blocker_pair_count':0,
        'unreviewed_blocker_pair_count':0,
        'blocker_localizations':[
            {'body_pair':pair,'samples':[]} for pair in reversed(pairs)
        ],
        'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
        'gate_promotions':[],
    }
    localization['proposal_sha256']=mechanics._canonical_sha256(localization)
    yaw_rad=math.radians(-105.0)
    profile={
        'schema':'rocell.virtual_commissioning_profile.v1',
        'status':'UNMEASURED_SENSITIVITY_OVERLAY',
        'simulation_only':True,'physical_release_effect':'NONE',
        'selection':{'source_mission_route_coverage_hash':'f'*64},
        'study_input':{
            'physical_placement_input':{
                'rear_clamp_contact_x_board_mm':385.0,
                'clamp_to_base_axis_x_mm':0.0,
                'rear_edge_to_base_axis_y_mm':75.0,
                'base_link_z_board_mm':70.1,
                'base_yaw_board_rad':yaw_rad,
                'matrix_row_major':[
                    math.cos(yaw_rad),-math.sin(yaw_rad),0.0,385.0,
                    math.sin(yaw_rad),math.cos(yaw_rad),0.0,532.0,
                    0.0,0.0,1.0,70.1,0.0,0.0,0.0,1.0,
                ],
            },
            'route_tool_lengths_mm':{'keyboard':120.0,'phone':100.0},
        },
    }
    search=mechanics.build_placement_tcp_search_plan(
        plan,route,receipt,localization,profile,
        virtual_profile_sha256=profile_sha256,
    )
    assert search['status']=='READY_FOR_ZERO_AUTHORITY_PLACEMENT_TCP_SCREENING'
    assert search['candidate_count']==82
    assert search['control_candidate_count']==1
    assert search['coarse_candidate_count']==81
    assert search['maximum_native_shortlist_count']==8
    assert len({item['candidate_id'] for item in search['candidates']})==82
    control=search['candidates'][0]
    assert control['candidate_id']==search['control_candidate_id']
    assert control['candidate_classification']=='RETAINED_ARM198_CONTROL'
    assert control['rear_edge_to_base_axis_y_mm']==75.0
    assert control['robot_placement_matrix_row_major']==pytest.approx(
        profile['study_input']['physical_placement_input']['matrix_row_major']
    )
    assert search['physical_blocker_pairs']==pairs
    assert search['collision_geometry_changed'] is False
    assert search['route_shape_changed'] is False
    assert search['hardware_access'] is search['physical_authority'] is False
    unsigned={key:value for key,value in search.items() if key!='plan_sha256'}
    assert search['plan_sha256']==mechanics._canonical_sha256(unsigned)

    tampered=dict(localization)
    tampered.pop('proposal_sha256')
    tampered['physical_solid_blocker_pair_count']=6
    tampered['proposal_sha256']=mechanics._canonical_sha256(tampered)
    with pytest.raises(mechanics.MechanicsContractError,match='lineage changed'):
        mechanics.build_placement_tcp_search_plan(
            plan,route,receipt,tampered,profile,
            virtual_profile_sha256=profile_sha256,
        )


def test_native_placement_tcp_selection_retains_raw_negative_result():
    mechanics=_load_key_mechanics()
    control='placement-tcp-control'
    alternative='placement-tcp-alternative'
    candidates=[
        {'candidate_id':control,'candidate_classification':'RETAINED_ARM198_CONTROL'},
        {'candidate_id':alternative,'candidate_classification':'HYPOTHESIS'},
    ]
    plan={
        'schema':mechanics.PLACEMENT_TCP_SEARCH_PLAN_SCHEMA,
        'status':'READY_FOR_ZERO_AUTHORITY_PLACEMENT_TCP_SCREENING',
        'control_candidate_id':control,'candidates':candidates,
        'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
        'gate_promotions':[],
    }
    plan['plan_sha256']=mechanics._canonical_sha256(plan)
    metrics={
        control:{'minimum_normalized_arm_joint_margin':0.2,
                 'maximum_position_error_mm':0.1},
        alternative:{'minimum_normalized_arm_joint_margin':0.3,
                     'maximum_position_error_mm':0.05},
    }
    screen={
        'schema':mechanics.PLACEMENT_TCP_SEARCH_SCREEN_SCHEMA,
        'status':'READY_FOR_SELECTED_NATIVE_ISAAC_REPLAY',
        'source_search_plan_sha256':plan['plan_sha256'],
        'native_shortlist_candidate_ids':[control,alternative],
        'outcomes':[{'candidate_id':item,'ik_metrics':metrics[item]}
                    for item in (control,alternative)],
        'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
        'gate_promotions':[],
    }
    screen['screen_sha256']=mechanics._canonical_sha256(screen)
    entries=[]
    for item in (control,alternative):
        entries.append({
            'candidate_id':item,
            'document_hashes':{
                'ik_receipt.json':('a' if item==control else 'b')*64,
                'policy_bound_collision_request.json':(
                    'c' if item==control else 'd'
                )*64,
            },
        })
    manifest={
        'schema':'tactevra.isaac_lm1_placement_tcp_native_shortlist.v1',
        'status':'READY_FOR_SELECTED_NATIVE_ISAAC_REPLAY',
        'source_search_plan_sha256':plan['plan_sha256'],
        'source_search_screen_sha256':screen['screen_sha256'],
        'entries':entries,'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
        'gate_promotions':[],
    }
    manifest['manifest_sha256']=mechanics._canonical_sha256(manifest)

    receipts={}
    for index,item in enumerate((control,alternative)):
        pair_count=7+index
        pairs=[[f'robot:link{number}','workcell:keyboard']
               for number in range(pair_count)]
        samples=[{
            'sample_id':f'{item}-sample-0',
            'raw_collision_pairs':pairs,
            'physical_solid_blocker_pairs':pairs,
        }]
        native={
            'schema':mechanics.TCP_ROUTE_PREDICATE_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA,
            'status':'DIAGNOSTIC_BLOCKERS_OBSERVED',
            'source_bindings':{
                'ik_receipt_sha256':entries[index]['document_hashes'][
                    'ik_receipt.json'
                ],
                'request_sha256':entries[index]['document_hashes'][
                    'policy_bound_collision_request.json'
                ],
            },
            'bounded_sample_count':1,'samples_with_overlaps':1,
            'physical_solid_blocker_pair_count':pair_count,
            'physical_solid_blocker_pairs':pairs,'samples':samples,
            'hardware_access':False,'physical_authority':False,
            'controller_commands':[],'hardware_writes':0,'physical_movements':0,
            'gate_promotions':[],
        }
        native['receipt_sha256']=mechanics._canonical_sha256(native)
        receipts[item]=native

    result=mechanics.retain_placement_tcp_native_results(
        plan,screen,manifest,receipts
    )
    assert result['status']=='NO_NATIVE_IMPROVEMENT_RETAINED'
    assert result['selected_candidate_id']==control
    assert result['native_improvement_over_control'] is False
    assert result['rank_order']==[control,alternative]
    assert result['retained_results'][1]['physical_solid_blocker_pair_count']==8
    assert result['retained_results'][1]['raw_native_samples']==receipts[alternative][
        'samples'
    ]
    assert result['gate_promotions']==[]
    unsigned={key:value for key,value in result.items() if key!='selection_sha256'}
    assert result['selection_sha256']==mechanics._canonical_sha256(unsigned)

    receipts[alternative]['samples'][0]['sample_id']='tampered'
    with pytest.raises(mechanics.MechanicsContractError,match='digest is invalid'):
        mechanics.retain_placement_tcp_native_results(
            plan,screen,manifest,receipts
        )


def test_route_shape_campaign_plan_is_bounded_and_preserves_endpoints():
    mechanics=_load_key_mechanics()
    control='placement-tcp-control'
    placement_plan={
        'schema':mechanics.PLACEMENT_TCP_SEARCH_PLAN_SCHEMA,
        'status':'READY_FOR_ZERO_AUTHORITY_PLACEMENT_TCP_SCREENING',
        'source_route_variant_request_sha256':'a'*64,
        'source_collision_candidate_sha256':'b'*64,
        'source_collision_pair_policy_sha256':'c'*64,
        'source_station_route_predicate_sha256':'d'*64,
        'source_toolchain_lock_sha256':'e'*64,
        'control_candidate_id':control,
        'route_shape_changed':False,
        'candidates':[{ 'candidate_id':control,
            'candidate_classification':'RETAINED_ARM198_CONTROL'}],
        'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
        'gate_promotions':[],
    }
    placement_plan['plan_sha256']=mechanics._canonical_sha256(placement_plan)
    selection={
        'schema':mechanics.PLACEMENT_TCP_NATIVE_SELECTION_SCHEMA,
        'status':'NO_NATIVE_IMPROVEMENT_RETAINED',
        'source_search_plan_sha256':placement_plan['plan_sha256'],
        'native_improvement_over_control':False,
        'selected_candidate_id':control,
        'retained_results':[{ 'candidate_id':control,
            'physical_solid_blocker_pair_count':7}],
        'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
        'gate_promotions':[],
    }
    selection['selection_sha256']=mechanics._canonical_sha256(selection)
    route={
        'schema':mechanics.TCP_CARTESIAN_SCHEDULE_SCHEMA,
        'route_variant_applied':True,'collision_geometry_changed':False,
        'samples':[
            {'sequence':0,'phase':'PARK'},
            {'sequence':1,'phase':'TRANSIT'},
            {'sequence':2,'phase':'TRANSIT'},
            {'sequence':3,'phase':'HOVER'},
            {'sequence':4,'phase':'CONTACT'},
            {'sequence':5,'phase':'RETRACT'},
        ],
        'hardware_access':False,'controller_commands':[],
        'hardware_writes':0,'physical_movements':0,
    }
    route['request_sha256']=mechanics._canonical_sha256(route)
    placement_plan.pop('plan_sha256')
    placement_plan['source_route_variant_request_sha256']=route['request_sha256']
    placement_plan['plan_sha256']=mechanics._canonical_sha256(placement_plan)
    selection.pop('selection_sha256')
    selection['source_search_plan_sha256']=placement_plan['plan_sha256']
    selection['selection_sha256']=mechanics._canonical_sha256(selection)

    plan=mechanics.build_route_shape_campaign_plan(
        placement_plan,selection,route
    )
    assert plan['status']=='READY_FOR_ZERO_AUTHORITY_ROUTE_SHAPE_SCREENING'
    assert plan['candidate_count']==9
    assert plan['control_candidate_count']==1
    assert plan['variant_candidate_count']==8
    assert plan['maximum_native_shortlist_count']==4
    assert plan['source_transit_sequences']==[1,2]
    assert plan['preserved_endpoint_sequences']==[0,3,4,5]
    assert plan['endpoint_scoring_separate'] is True
    assert plan['placement_tcp_changed'] is False
    assert plan['collision_geometry_changed'] is False
    assert plan['non_transit_endpoints_changed'] is False
    assert len({item['candidate_id'] for item in plan['candidates']})==9
    control_route=plan['candidates'][0]
    assert control_route['candidate_id']==plan['control_candidate_id']
    assert control_route['source_request_reused_exactly'] is True
    assert control_route['xy_corridor_topology']=='DIRECT_LINEAR'
    assert control_route['corridor_height_board_mm']==70.0
    assert control_route['corridor_height_ramp_fraction'] is None
    assert control_route['transit_resampling']=='SOURCE_REQUEST_EXACT'
    assert plan['hardware_access'] is plan['physical_authority'] is False
    unsigned={key:value for key,value in plan.items() if key!='plan_sha256'}
    assert plan['plan_sha256']==mechanics._canonical_sha256(unsigned)

    tampered=dict(selection)
    tampered.pop('selection_sha256')
    tampered['native_improvement_over_control']=True
    tampered['selection_sha256']=mechanics._canonical_sha256(tampered)
    with pytest.raises(mechanics.MechanicsContractError,match='lineage changed'):
        mechanics.build_route_shape_campaign_plan(
            placement_plan,tampered,route
        )


def test_route_shape_materialization_changes_only_declared_transit_domain():
    mechanics=_load_key_mechanics()
    samples=[
        {'sequence':0,'phase':'PARK','time_from_start_ns':0,
         'expected_tool_tip_board_mm':[0.0,0.0,10.0]},
        {'sequence':1,'phase':'TRANSIT','time_from_start_ns':1,
         'expected_tool_tip_board_mm':[1.0,1.0,30.0]},
        {'sequence':2,'phase':'TRANSIT','time_from_start_ns':2,
         'expected_tool_tip_board_mm':[2.0,2.0,40.0]},
        {'sequence':3,'phase':'HOVER','time_from_start_ns':3,
         'expected_tool_tip_board_mm':[10.0,20.0,20.0]},
    ]
    source={
        'schema':mechanics.TCP_CARTESIAN_SCHEDULE_SCHEMA,
        'route_variant_applied':True,'collision_geometry_changed':False,
        'samples':samples,'limitations':[],
        'hardware_access':False,'controller_commands':[],
        'hardware_writes':0,'physical_movements':0,
    }
    source['request_sha256']=mechanics._canonical_sha256(source)

    def candidate(topology,height,source_exact=False):
        value={
            'candidate_classification':('CONTROL' if source_exact else 'VARIANT'),
            'xy_corridor_topology':topology,
            'corridor_height_board_mm':height,
            'corridor_height_ramp_fraction':None if source_exact else 0.25,
            'transit_resampling':('SOURCE_REQUEST_EXACT' if source_exact else
                'ARC_LENGTH_PIECEWISE_LINEAR_WITH_SYMMETRIC_Z_RAMPS'),
            'source_request_reused_exactly':source_exact,
            'non_transit_endpoints_changed':False,
            'sample_count_changed':False,'timing_changed':False,
        }
        value['candidate_id']='route-shape-'+mechanics._canonical_sha256(value)[:16]
        return value

    control=candidate('DIRECT_LINEAR',70.0,True)
    direct=candidate('DIRECT_LINEAR',90.0)
    dogleg=candidate('X_THEN_Y',90.0)
    plan={
        'schema':mechanics.ROUTE_SHAPE_CAMPAIGN_PLAN_SCHEMA,
        'status':'READY_FOR_ZERO_AUTHORITY_ROUTE_SHAPE_SCREENING',
        'source_route_variant_request_sha256':source['request_sha256'],
        'source_sample_count':4,
        'source_transit_sequences':[1,2],
        'preserved_endpoint_sequences':[0,3],
        'candidates':[control,direct,dogleg],
        'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
        'gate_promotions':[],
    }
    plan['plan_sha256']=mechanics._canonical_sha256(plan)

    retained=mechanics.materialize_route_shape_candidate(
        plan,source,control['candidate_id'])
    assert retained['samples']==samples
    assert retained['changed_cartesian_sequences']==[]

    materialized=mechanics.materialize_route_shape_candidate(
        plan,source,direct['candidate_id'])
    assert materialized['samples'][0]==samples[0]
    assert materialized['samples'][3]==samples[3]
    assert materialized['samples'][1]['expected_tool_tip_board_mm']==pytest.approx(
        [10.0/3.0,20.0/3.0,90.0]
    )
    assert materialized['samples'][2]['expected_tool_tip_board_mm']==pytest.approx(
        [20.0/3.0,40.0/3.0,90.0]
    )
    assert materialized['changed_cartesian_sequences']==[1,2]
    assert materialized['non_transit_endpoints_changed'] is False
    assert materialized['placement_tcp_changed'] is False
    assert materialized['collision_geometry_changed'] is False

    orthogonal=mechanics.materialize_route_shape_candidate(
        plan,source,dogleg['candidate_id'])
    assert orthogonal['samples'][1]['expected_tool_tip_board_mm']==pytest.approx(
        [10.0,0.0,90.0]
    )
    assert orthogonal['samples'][2]['expected_tool_tip_board_mm']==pytest.approx(
        [10.0,10.0,90.0]
    )

    changed=dict(plan)
    changed.pop('plan_sha256')
    changed['source_transit_sequences']=[2]
    changed['plan_sha256']=mechanics._canonical_sha256(changed)
    with pytest.raises(mechanics.MechanicsContractError,match='transit domain'):
        mechanics.materialize_route_shape_candidate(
            changed,source,direct['candidate_id']
        )


def test_route_shape_ranking_keeps_transit_and_endpoint_blockers_separate():
    mechanics=_load_key_mechanics()

    def outcome(candidate_id,transit_pairs,transit_samples,endpoint_pairs,
                margin,error):
        return {
            'candidate_id':candidate_id,
            'transit_physical_blocker_pair_count':transit_pairs,
            'transit_blocked_sample_count':transit_samples,
            'endpoint_physical_blocker_pair_count':endpoint_pairs,
            'ik_metrics':{
                'minimum_normalized_arm_joint_margin':margin,
                'maximum_position_error_mm':error,
            },
        }

    endpoint_only=outcome('endpoint-only',0,0,1,0.5,0.01)
    transit_blocked=outcome('transit-blocked',1,1,0,0.9,0.001)
    lower_margin=outcome('lower-margin',0,0,0,0.2,0.01)
    higher_margin=outcome('higher-margin',0,0,0,0.3,0.02)
    ranked=sorted(
        [transit_blocked,endpoint_only,lower_margin,higher_margin],
        key=mechanics._route_shape_candidate_rank_key,
    )
    assert [item['candidate_id'] for item in ranked]==[
        'higher-margin','lower-margin','endpoint-only','transit-blocked'
    ]


def test_route_shape_shortlist_materializes_exact_retained_evidence(
    tmp_path,monkeypatch
):
    mechanics=_load_key_mechanics()
    candidate_id='route-shape-shortlisted'
    candidate={'candidate_id':candidate_id,
               'candidate_classification':'VARIANT'}
    plan={
        'schema':mechanics.ROUTE_SHAPE_CAMPAIGN_PLAN_SCHEMA,
        'status':'READY_FOR_ZERO_AUTHORITY_ROUTE_SHAPE_SCREENING',
        'candidates':[candidate],'maximum_native_shortlist_count':4,
        'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
        'gate_promotions':[],
    }
    plan['plan_sha256']=mechanics._canonical_sha256(plan)
    request={'route_shape_candidate_id':candidate_id}
    request['request_sha256']=mechanics._canonical_sha256(request)
    ik={
        'route_shape_candidate_id':candidate_id,
        'ik_all_samples_accepted':True,
    }
    ik['receipt_sha256']=mechanics._canonical_sha256(ik)
    screen={
        'schema':mechanics.ROUTE_SHAPE_CAMPAIGN_SCREEN_SCHEMA,
        'status':'READY_FOR_SELECTED_NATIVE_ISAAC_REPLAY',
        'source_campaign_plan_sha256':plan['plan_sha256'],
        'native_shortlist_candidate_ids':[candidate_id],
        'outcomes':[{
            'candidate_id':candidate_id,
            'request_sha256':request['request_sha256'],
            'ik_receipt_sha256':ik['receipt_sha256'],
        }],
        'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
        'gate_promotions':[],
    }
    screen['screen_sha256']=mechanics._canonical_sha256(screen)
    collision={'candidate_sha256':'c'*64}
    policy={'policy_sha256':'p'*64}
    toolchain={'schema':'toolchain'}
    raw={'request_sha256':'r'*64}
    bound={'request_sha256':'b'*64}
    monkeypatch.setattr(
        mechanics,'build_robot_tcp_collision_replay_request',
        lambda actual_ik,actual_collision,actual_lock:raw,
    )
    monkeypatch.setattr(
        mechanics,'bind_collision_pair_policy_request',
        lambda actual_request,actual_policy:bound,
    )

    manifest=mechanics.materialize_route_shape_native_shortlist(
        plan,screen,{candidate_id:(request,ik)},collision,policy,toolchain,
        output_dir=tmp_path,
    )
    assert manifest['schema']==mechanics.ROUTE_SHAPE_NATIVE_SHORTLIST_SCHEMA
    assert manifest['shortlist_count']==1
    assert manifest['entries'][0]['candidate_id']==candidate_id
    assert manifest['entries'][0]['document_hashes']=={
        'cartesian_request.json':request['request_sha256'],
        'ik_receipt.json':ik['receipt_sha256'],
        'collision_request.json':raw['request_sha256'],
        'policy_bound_collision_request.json':bound['request_sha256'],
    }
    assert set(path.name for path in (tmp_path/candidate_id).iterdir())=={
        'cartesian_request.json','ik_receipt.json','collision_request.json',
        'policy_bound_collision_request.json',
    }
    unsigned={key:value for key,value in manifest.items()
              if key!='manifest_sha256'}
    assert manifest['manifest_sha256']==mechanics._canonical_sha256(unsigned)


def test_route_shape_native_selection_retains_mixed_one_attempt_outcome():
    mechanics=_load_key_mechanics()
    failed='route-shape-failed'
    completed='route-shape-completed'
    candidates=[
        {'candidate_id':failed,'candidate_classification':'VARIANT'},
        {'candidate_id':completed,'candidate_classification':'VARIANT'},
    ]
    plan={
        'schema':mechanics.ROUTE_SHAPE_CAMPAIGN_PLAN_SCHEMA,
        'status':'READY_FOR_ZERO_AUTHORITY_ROUTE_SHAPE_SCREENING',
        'candidates':candidates,
        'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
        'gate_promotions':[],
    }
    plan['plan_sha256']=mechanics._canonical_sha256(plan)
    screen={
        'schema':mechanics.ROUTE_SHAPE_CAMPAIGN_SCREEN_SCHEMA,
        'status':'READY_FOR_SELECTED_NATIVE_ISAAC_REPLAY',
        'source_campaign_plan_sha256':plan['plan_sha256'],
        'native_shortlist_candidate_ids':[failed,completed],
        'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
        'gate_promotions':[],
    }
    screen['screen_sha256']=mechanics._canonical_sha256(screen)
    entries=[]
    for rank,candidate in enumerate(candidates,start=1):
        entries.append({
            'candidate_id':candidate['candidate_id'],'candidate':candidate,
            'rank':rank,
            'document_hashes':{
                'ik_receipt.json':str(rank)*64,
                'policy_bound_collision_request.json':str(rank+2)*64,
            },
        })
    manifest={
        'schema':mechanics.ROUTE_SHAPE_NATIVE_SHORTLIST_SCHEMA,
        'status':'READY_FOR_SELECTED_NATIVE_ISAAC_REPLAY',
        'source_campaign_plan_sha256':plan['plan_sha256'],
        'source_campaign_screen_sha256':screen['screen_sha256'],
        'entries':entries,
        'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
        'gate_promotions':[],
    }
    manifest['manifest_sha256']=mechanics._canonical_sha256(manifest)
    pairs=[[f'robot:link{number}','workcell:board_solid']
           for number in range(7)]
    control={
        'schema':mechanics.TCP_ROUTE_PREDICATE_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA,
        'status':'DIAGNOSTIC_BLOCKERS_OBSERVED',
        'physical_solid_blocker_pair_count':7,
        'physical_solid_blocker_pairs':pairs,'samples':[{'sample_id':'control'}],
        'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
        'gate_promotions':[],
    }
    control['receipt_sha256']=mechanics._canonical_sha256(control)
    native={
        'schema':mechanics.TCP_ROUTE_PREDICATE_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA,
        'status':'DIAGNOSTIC_BLOCKERS_OBSERVED',
        'source_bindings':{
            'ik_receipt_sha256':entries[1]['document_hashes']['ik_receipt.json'],
            'request_sha256':entries[1]['document_hashes'][
                'policy_bound_collision_request.json'
            ],
        },
        'bounded_sample_count':1,'samples_with_overlaps':1,
        'physical_solid_blocker_pair_count':7,
        'physical_solid_blocker_pairs':pairs,
        'planning_envelope_blocker_pair_count':1,
        'planning_envelope_blocker_pairs':[
            ['robot:link4','workcell:station:keyboard_left']
        ],
        'policy_excluded_pair_count':5,'unreviewed_blocker_pair_count':0,
        'samples':[{'sample_id':'native','raw_collision_pairs':pairs}],
        'hardware_access':False,'physical_authority':False,
        'controller_commands':[],'hardware_writes':0,'physical_movements':0,
        'gate_promotions':[],
    }
    native['receipt_sha256']=mechanics._canonical_sha256(native)
    error={
        'status':'ERROR','type':'MechanicsContractError',
        'message':'collision pair policy boundary changed',
    }

    result=mechanics.retain_route_shape_native_results(
        plan,screen,manifest,control,{failed:error,completed:native}
    )
    assert result['status']==(
        'INCOMPLETE_NATIVE_REPLAY_NO_IMPROVEMENT_RETAINED'
    )
    assert result['attempted_candidate_count']==2
    assert result['completed_native_replay_count']==1
    assert result['failed_pre_admission_count']==1
    assert result['native_improvement_over_control'] is False
    assert result['selected_candidate_id'] is None
    assert result['automatic_retries_performed']==0
    assert result['failed_attempts'][0]['candidate_id']==failed
    assert result['failed_attempts'][0]['automatic_retry_performed'] is False
    assert result['retained_results'][0]['raw_native_samples']==native['samples']
    unsigned={key:value for key,value in result.items()
              if key!='selection_sha256'}
    assert result['selection_sha256']==mechanics._canonical_sha256(unsigned)

    v4_result=mechanics.retain_route_shape_native_results(
        plan,screen,manifest,control,{failed:error,completed:native},
        require_route_predicate_receipts=True,
    )
    assert v4_result['schema']==mechanics.ROUTE_SHAPE_V4_NATIVE_SELECTION_SCHEMA
    assert v4_result['status']==(
        'INCOMPLETE_V4_NATIVE_REPLAY_NO_IMPROVEMENT_RETAINED'
    )
    assert v4_result['retained_results'][0][
        'station_route_predicate_applied'
    ] is True


def test_collision_blockers_localize_to_retained_cartesian_context():
    mechanics=_load_key_mechanics()
    cartesian={
        'schema':'tactevra.isaac_lm1_robot_tcp_cartesian_schedule_request.v1',
        'status':'READY_FOR_IK_QUALIFICATION',
        'sample_count':3,
        'samples':[
            {
                'sequence':0,'action_index':0,'phase':'approach',
                'target_id':'H','phase_endpoint':False,
                'expected_tool_tip_board_mm':[210.0,150.0,35.0],
            },
            {
                'sequence':1,'action_index':0,'phase':'transition',
                'target_id':'H','phase_endpoint':True,
                'expected_tool_tip_board_mm':[216.0,154.0,20.0],
            },
            {
                'sequence':2,'action_index':1,'phase':'retract',
                'target_id':'SPACE','phase_endpoint':True,
                'expected_tool_tip_board_mm':[224.0,112.0,35.0],
            },
        ],
        'hardware_access':False,'hardware_writes':0,'physical_movements':0,
    }
    cartesian['request_sha256']=mechanics._canonical_sha256(cartesian)
    joints=[
        {'joint1':0.1,'joint2':0.2},
        {'joint1':0.2,'joint2':0.3},
        {'joint1':0.3,'joint2':0.4},
    ]
    bounded=[
        {
            'sample_sequence':index,'sample_id':f'sample-{index:03d}',
            'source_segment_index':index,'interpolation_ratio':1.0,
            'subdivision_count':1,'subdivision_index':1,
            'joint_positions_rad':joint,
        }
        for index,joint in enumerate(joints)
    ]
    request={
        'schema':'tactevra.isaac_lm1_robot_tcp_collision_replay_request.v2',
        'status':'READY_FOR_ZERO_AUTHORITY_COLLISION_DIAGNOSTIC',
        'source_request_sha256':cartesian['request_sha256'],
        'bounded_sample_count':len(bounded),'bounded_samples':bounded,
        'diagnostic_only':True,'installed_collision_qualified':False,
        'continuous_collision_proven':False,
    }
    request['request_sha256']=mechanics._canonical_sha256(request)
    physical=['robot:link4','workcell:keyboard']
    planning=['robot:gripper','workcell:station:keyboard_left']
    observed=[]
    for index,row in enumerate(bounded):
        observed.append({
            'sample_sequence':index,'sample_id':row['sample_id'],
            'source_segment_index':row['source_segment_index'],
            'joint_positions_rad':row['joint_positions_rad'],
            'physical_solid_blocker_pairs':[physical] if index < 2 else [],
            'planning_envelope_blocker_pairs':[planning] if index > 0 else [],
            'unreviewed_blocker_pairs':[],
        })
    receipt={
        'schema':'tactevra.isaac_lm1_robot_tcp_collision_diagnostic.v2',
        'status':'DIAGNOSTIC_BLOCKERS_OBSERVED',
        'source_bindings':{'request_sha256':request['request_sha256']},
        'bounded_sample_count':len(observed),'samples':observed,
        'physical_solid_blocker_pairs':[physical],
        'physical_solid_blocker_pair_count':1,
        'planning_envelope_blocker_pairs':[planning],
        'planning_envelope_blocker_pair_count':1,
        'unreviewed_blocker_pairs':[],
        'unreviewed_blocker_pair_count':0,
        'collision_pair_policy_applied':True,
        'installed_collision_qualified':False,
        'continuous_collision_proven':False,'gate_promotions':[],
    }
    receipt['receipt_sha256']=mechanics._canonical_sha256(receipt)

    proposal=mechanics.build_collision_blocker_localization(
        receipt,request,cartesian,
    )
    assert proposal['status']=='REVIEW_REQUIRED_COLLISION_BLOCKER_REMEDIATION'
    assert proposal['localized_blocker_pair_count']==2
    assert proposal['physical_solid_blocker_pair_count']==1
    assert proposal['planning_envelope_blocker_pair_count']==1
    assert proposal['unreviewed_blocker_pair_count']==0
    assert proposal['physical_geometry_refinement_robot_bodies']==['robot:link4']
    assert proposal['planning_region_bodies']==[
        'workcell:station:keyboard_left'
    ]
    rows={tuple(row['body_pair']):row for row in proposal['blocker_localizations']}
    assert rows[tuple(physical)]['sample_sequence_ranges']==[{'start':0,'end':1}]
    assert rows[tuple(physical)]['phase_counts']=={'approach':1,'transition':1}
    assert rows[tuple(planning)]['source_segment_ranges']==[{'start':1,'end':2}]
    assert rows[tuple(planning)]['target_counts']=={'H':1,'SPACE':1}
    assert proposal['proposal_applied'] is False
    assert proposal['hardware_access'] is proposal['physical_authority'] is False
    assert proposal['gate_promotions']==[]
    unsigned={key:value for key,value in proposal.items() if key!='proposal_sha256'}
    assert proposal['proposal_sha256']==mechanics._canonical_sha256(unsigned)

    receipt['schema']='tactevra.isaac_lm1_robot_tcp_collision_diagnostic.v3'
    receipt['source_bindings']['collision_candidate_sha256']='candidate-sha'
    for index,sample in enumerate(receipt['samples']):
        primitive_pairs=[]
        if index < 2:
            primitive_pairs.append({
                'body_pair':physical,'primitive_indices':[0,0],
            })
        if index > 0:
            primitive_pairs.append({
                'body_pair':planning,'primitive_indices':[1,0],
            })
        sample['raw_collision_primitive_pair_count']=len(primitive_pairs)
        sample['raw_collision_primitive_pairs']=primitive_pairs
        sample['raw_collision_pairs']=[
            item['body_pair'] for item in primitive_pairs
        ]
    receipt['unique_collision_primitive_pair_count']=2
    receipt['unique_collision_primitive_pairs']=[
        {'body_pair':physical,'primitive_indices':[0,0]},
        {'body_pair':planning,'primitive_indices':[1,0]},
    ]
    receipt['primitive_pair_observations']=[
        {
            'body_pair':physical,'primitive_indices':[0,0],
            'sample_count':2,'persistent_across_all_samples':False,
        },
        {
            'body_pair':planning,'primitive_indices':[1,0],
            'sample_count':2,'persistent_across_all_samples':False,
        },
    ]
    receipt['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in receipt.items() if key!='receipt_sha256'
    })
    attributed=mechanics.build_collision_blocker_localization(
        receipt,request,cartesian,
    )
    assert attributed['primitive_attribution_available'] is True
    assert attributed['localized_blocker_primitive_pair_count']==2
    assert attributed['source_collision_candidate_sha256']=='candidate-sha'
    attributed_rows={
        tuple(row['body_pair']):row
        for row in attributed['blocker_localizations']
    }
    assert attributed_rows[tuple(physical)]['primitive_localizations']==[{
        'primitive_indices':[0,0],
        'sample_count':2,
        'sample_sequence_ranges':[{'start':0,'end':1}],
    }]
    assert attributed_rows[tuple(planning)]['primitive_localizations']==[{
        'primitive_indices':[1,0],
        'sample_count':2,
        'sample_sequence_ranges':[{'start':1,'end':2}],
    }]

    receipt['samples'][0]['source_segment_index']=1
    receipt['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in receipt.items() if key!='receipt_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='sample lineage'):
        mechanics.build_collision_blocker_localization(receipt,request,cartesian)
