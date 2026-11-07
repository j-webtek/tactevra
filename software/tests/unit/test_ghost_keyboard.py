import json
import hashlib
import importlib.util
import inspect
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
    assert result['commanded_key']=='H'
    assert result['resolved_key']=='H'
    assert result['native_contact_observed']
    assert result['native_contact_step_count']==4


def test_native_displacement_uses_the_requested_representative_key_region():
    mechanics=_load_key_mechanics()
    profile=mechanics.build_profile(ROOT/'software/config/nominal_target_profiles.json')
    compressions=[0.0,1.0,2.2,3.0,1.2,0.0]
    rows=[{
        'time_s':index*0.02,
        'key_center_z_m':0.018-compression/1000,
        'tip_key_separation_m':-0.0001 if compression else 0.001,
    } for index,compression in enumerate(compressions)]
    result=mechanics.assess_native_key_trace(
        profile,rows,rest_key_z_m=0.018,target_id='PERIOD'
    )
    assert result['accepted']
    assert result['commanded_key']=='PERIOD'
    assert result['resolved_key']=='PERIOD'
    assert result['native_contact_observed']

    with pytest.raises(mechanics.MechanicsContractError,match='is unavailable'):
        mechanics.assess_native_key_trace(
            profile,rows,rest_key_z_m=0.018,target_id='NOT_A_KEY'
        )


def _arm207_plan_fixture(mechanics):
    def signed(document, field):
        document[field]=mechanics._canonical_sha256(document)
        return document

    profile=signed({
        'schema':mechanics.PROFILE_SCHEMA,
        'authority':{'hardware':False,'motion':False,'physical_keyboard_qualification':False},
        'mechanics_prior':{'release_mm':{'nominal':1.2}},
    },'profile_sha256')
    request=signed({
        'schema':mechanics.TCP_CARTESIAN_SCHEDULE_SCHEMA,
        'status':'READY_FOR_IK_QUALIFICATION','route_shape_candidate_id':'route-a',
        'profile_sha256':profile['profile_sha256'],'sample_count':3,
        'samples':[
            {'sequence':0,'time_from_start_ns':0,'phase':'CONTACT','target_id':'H','action_index':0,'phase_endpoint':True},
            {'sequence':1,'time_from_start_ns':1,'phase':'RETRACT','target_id':'H','action_index':0,'phase_endpoint':True},
            {'sequence':2,'time_from_start_ns':2,'phase':'CONTACT','target_id':'H','action_index':1,'phase_endpoint':True},
        ],
        'authority':{'hardware':False,'motion':False,'physical_keyboard_qualification':False},
        'hardware_access':False,'hardware_writes':0,'physical_movements':0,'controller_commands':[],
    },'request_sha256')
    joints=['base_link_to_link1','link1_to_link2','link2_to_link3','link3_to_link4','link4_to_link5']
    results=[]
    for sample in request['samples']:
        results.append({
            'accepted':True,'phase':sample['phase'],'action_index':sample['action_index'],
            'solution_arm_joint_positions_rad':{name:index/10 for index,name in enumerate(joints)},
        })
    ik=signed({
        'schema':mechanics.TCP_IK_SCREEN_SCHEMA,'status':'READY_FOR_COLLISION_QUALIFICATION',
        'source_request_sha256':request['request_sha256'],'route_shape_candidate_id':'route-a',
        'sample_count':3,'joint_results':results,'placement_tcp_candidate_id':'place-a',
        'robot_placement_matrix_row_major':[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],
        'hardware_access':False,'hardware_writes':0,'physical_authority':False,
        'physical_movements':0,'controller_commands':[],
    },'receipt_sha256')
    fixed_plan=signed({
        'schema':mechanics.FIXED_BASE_COLLISION_REPLAY_PLAN_SCHEMA,
        'status':'READY_FOR_FIXED_BASE_ZERO_AUTHORITY_NATIVE_REPLAY',
        'candidates':[{'candidate_id':'route-a','source_request_sha256':request['request_sha256']}],
    },'plan_sha256')
    usd=b'governed-usd'
    imported=signed({
        'schema':'tactevra.isaac_sim_urdf_import.v1',
        'external_files':[{'sha256':hashlib.sha256(usd).hexdigest(),'size_bytes':len(usd)}],
        'articulation_root_normalization':{'expected_live_dof_order':joints+['link5_to_gripper_link']},
    },'receipt_sha256')
    fixed=signed({
        'schema':mechanics.TCP_FIXED_BASE_COLLISION_DIAGNOSTIC_RECEIPT_SCHEMA,
        'fixed_base_mechanism':'USD_FIXED_JOINT_TO_WORLD',
        'source_bindings':{
            'ik_receipt_sha256':ik['receipt_sha256'],
            'fixed_base_replay_plan_sha256':fixed_plan['plan_sha256'],
            'robot_import_receipt_sha256':imported['receipt_sha256'],
            'robot_usd_sha256':hashlib.sha256(usd).hexdigest(),
        },
        'root_pose_invariant':{'observation_count':1,'expected_observation_count':1,'observations':[{'passed':True}]},
        'hardware_access':False,'hardware_writes':0,'physical_authority':False,
        'physical_movements':0,'controller_commands':[],'gate_promotions':[],
    },'receipt_sha256')
    placement=signed({
        'schema':mechanics.PLACEMENT_TCP_NATIVE_SELECTION_SCHEMA,
        'selected_candidate_id':'place-a','control_candidate_id':'place-a',
        'hardware_access':False,'physical_authority':False,
    },'selection_sha256')
    native=signed({
        'schema':mechanics.NATIVE_RECEIPT_SCHEMA,'status':'PASS',
        'profile_sha256':profile['profile_sha256'],
        'assessment':{'resolved_key':'H','accepted':True,'native_contact_observed':True},
    },'receipt_sha256')
    drive={'schema':mechanics.GEOMETRY_PRIOR_PROFILE_SCHEMA,'status':'PROVISIONAL_SIMULATION_ONLY','simulation_only':True,'physical_authority':False}
    drive_raw=json.dumps(drive,sort_keys=True).encode()
    selected={
        'candidate_id':'route-a','learning_baseline_rank':1,
        'fixed_base_collision_passed':True,'key_mechanics_passed':True,
        'source_cartesian_request_sha256':request['request_sha256'],
        'source_ik_receipt_sha256':ik['receipt_sha256'],
        'source_fixed_base_v5_receipt_sha256':fixed['receipt_sha256'],
    }
    selection=signed({
        'schema':mechanics.KEY_MECHANICS_LEARNING_BASELINE_SELECTION_SCHEMA,
        'status':'SELECTED_ZERO_AUTHORITY_SIMULATION_LEARNING_BASELINE',
        'selection_scope':'SIMULATION_LEARNING_BASELINE_ONLY',
        'next_action':'RUN_DRIVE_CONTROLLED_ROBOT_H_KEY_REPLAY_FOR_SELECTED_BASELINE',
        'selected_candidate_id':'route-a','selected_candidate_rank':1,
        'ranked_candidates':[selected],
        'source_key_mechanics_profile_sha256':profile['profile_sha256'],
        'hardware_access':False,'hardware_writes':0,'physical_authority':False,
        'physical_movements':0,'controller_commands':[],'gate_promotions':[],
    },'selection_sha256')
    return [selection,request,ik,fixed,fixed_plan,placement,profile,native,drive,drive_raw,usd,imported]


def test_arm207_plan_binds_selected_targets_and_zero_authority():
    mechanics=_load_key_mechanics()
    plan=mechanics.build_drive_controlled_robot_h_replay_plan(*_arm207_plan_fixture(mechanics))
    assert plan['status']=='READY_FOR_ZERO_AUTHORITY_NATIVE_ROBOT_H_REPLAY'
    assert plan['selected_candidate_id']=='route-a'
    assert plan['sample_count']==3
    assert plan['h_contact_endpoint_sequences']==[0,2]
    assert plan['joint_targets'][0]['joint_position_target_rad']==pytest.approx([0,.1,.2,.3,.4,0])
    assert plan['execution_contract']['post_initialization_state_teleports']==0
    assert plan['controller_commands']==[] and plan['hardware_writes']==0


def test_arm207_plan_rejects_nonselected_or_tampered_evidence():
    mechanics=_load_key_mechanics()
    values=_arm207_plan_fixture(mechanics)
    values[1]['route_shape_candidate_id']='other'
    values[1]['request_sha256']=mechanics._canonical_sha256({k:v for k,v in values[1].items() if k!='request_sha256'})
    with pytest.raises(mechanics.MechanicsContractError):
        mechanics.build_drive_controlled_robot_h_replay_plan(*values)


def test_arm207_plan_rejects_authority_escalation():
    mechanics=_load_key_mechanics()
    values=_arm207_plan_fixture(mechanics)
    values[0]['physical_authority']=True
    values[0]['selection_sha256']=mechanics._canonical_sha256({k:v for k,v in values[0].items() if k!='selection_sha256'})
    with pytest.raises(mechanics.MechanicsContractError,match='selection boundary'):
        mechanics.build_drive_controlled_robot_h_replay_plan(*values)


def _arm208_feedback_fixture(mechanics):
    def signed(document, field):
        document[field]=mechanics._canonical_sha256(document)
        return document

    profile=signed({
        'schema':mechanics.PROFILE_SCHEMA,
        'mechanics_prior':{
            'activation_mm':{'nominal':2.0},
            'release_mm':{'nominal':1.2},
            'travel_mm':{'nominal':3.5},
        },
        'authority':{
            'hardware':False,'motion':False,
            'physical_keyboard_qualification':False,
        },
        'target_plane_z_board_mm':21.0,
        'regions':{
            key:{'center_board_xy_mm':center,'half_extent_mm':half}
            for key,center,half in (
                ('H',[216.55,154.0],[7.0,7.0]),
                ('1',[107.0,196.0],[7.0,7.0]),
                ('SPACE',[224.0,112.0],[48.0,7.0]),
                ('ENTER',[335.5,154.0],[13.0,7.0]),
                ('PERIOD',[283.2,133.0],[7.0,7.0]),
            )
        },
    },'profile_sha256')
    targets=[]
    for sequence in range(40):
        row={
            'sequence':sequence,'time_from_start_ns':sequence*100_000_000,
            'phase':'TRANSIT','target_id':None,'action_index':None,
            'phase_endpoint':False,'joint_position_target_rad':[0.0]*6,
        }
        targets.append(row)
    phases={
        34:('HOVER',0,[0.0]*6),
        35:('CONTACT',0,[0.0,0.27,0.09,-0.36,0.0,0.0]),
        36:('RETRACT',0,[0.0]*6),
        37:('HOVER',1,[0.0]*6),
        38:('CONTACT',1,[0.0,0.27,0.09,-0.36,0.0,0.0]),
        39:('RETRACT',1,[0.0]*6),
    }
    for sequence,(phase,action,target) in phases.items():
        targets[sequence].update({
            'phase':phase,'target_id':'H','action_index':action,
            'phase_endpoint':True,'joint_position_target_rad':target,
        })
    plan=signed({
        'schema':mechanics.DRIVE_CONTROLLED_ROBOT_H_REPLAY_PLAN_SCHEMA,
        'status':'READY_FOR_ZERO_AUTHORITY_NATIVE_ROBOT_H_REPLAY',
        'selected_candidate_id':'route-a','joint_order':['j0','j1','j2','j3','j4','j5'],
        'sample_count':len(targets),'h_contact_endpoint_sequences':[35,38],
        'joint_targets':targets,'robot_placement_matrix_row_major':[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],
        'source_bindings':{'key_mechanics_profile_sha256':profile['profile_sha256']},
        'execution_contract':{
            'initial_joint_state_placement_count':1,
            'post_initialization_state_teleports':0,
            'subsequent_joint_commands':'ARTICULATION_POSITION_TARGETS_ONLY',
            'key_motion_source':'NATIVE_CONTACT_ONLY',
            'root_pose_invariant_required_after_every_sample':True,
        },
        'hardware_access':False,'physical_authority':False,'controller_commands':[],
        'hardware_writes':0,'physical_movements':0,'gate_promotions':[],
        'limitations':['simulation_only'],
    },'plan_sha256')
    receipt=signed({
        'schema':mechanics.DRIVE_CONTROLLED_ROBOT_H_REPLAY_RECEIPT_SCHEMA,
        'status':'BLOCKED_NATIVE_ROBOT_H_REPLAY','source_plan_sha256':plan['plan_sha256'],
        'physics_dt_s':1/120,'state_teleports_after_initialization':0,
        'action_assessments':[
            {'action_index':0,'assessment':{
                'profile_sha256':profile['profile_sha256'],'disposition':'EXCESSIVE_TRAVEL',
                'native_contact_observed':True,'activation_count':1,
                'final_compression_mm':2.36,'max_compression_mm':3.78,
            }},
            {'action_index':1,'assessment':{
                'profile_sha256':profile['profile_sha256'],'disposition':'EXCESSIVE_TRAVEL',
                'native_contact_observed':True,'activation_count':0,
                'final_compression_mm':2.37,'max_compression_mm':3.75,
            }},
        ],
        'hardware_access':False,'physical_authority':False,'controller_commands':[],
        'hardware_writes':0,'physical_movements':0,'gate_promotions':[],
    },'receipt_sha256')
    return plan,receipt,profile


def test_arm208_feedback_adapter_changes_only_contact_depth_and_release_dwell():
    mechanics=_load_key_mechanics()
    plan,receipt,profile=_arm208_feedback_fixture(mechanics)
    adapted=mechanics.build_feedback_adapted_robot_h_replay_plan(plan,receipt,profile)
    assert adapted['status']=='READY_FOR_ZERO_AUTHORITY_FEEDBACK_ADAPTED_NATIVE_H_REPLAY'
    assert adapted['feedback_adaptation']['adapted_contact_sequences']==[35,38]
    assert adapted['feedback_adaptation']['release_dwell_sequences']==[36,39]
    assert adapted['feedback_adaptation']['adapted_commanded_depth_mm']==pytest.approx(1.62)
    assert adapted['feedback_adaptation']['release_dwell_steps']==240
    ratio=1.62/2.7
    assert adapted['joint_targets'][35]['joint_position_target_rad']==pytest.approx([
        0.0,0.27*ratio,0.09*ratio,-0.36*ratio,0.0,0.0,
    ])
    assert adapted['joint_targets'][38]['joint_position_target_rad']==pytest.approx(
        adapted['joint_targets'][35]['joint_position_target_rad']
    )
    assert adapted['joint_targets'][36]['additional_hold_steps']==240
    assert adapted['joint_targets'][39]['additional_hold_steps']==240
    assert all(
        adapted['joint_targets'][index]['joint_position_target_rad']
        == plan['joint_targets'][index]['joint_position_target_rad']
        for index in range(40) if index not in (35,38)
    )
    assert adapted['controller_commands']==[] and adapted['hardware_writes']==0


def test_arm208_feedback_adapter_rejects_tampering_and_authority_escalation():
    mechanics=_load_key_mechanics()
    plan,receipt,profile=_arm208_feedback_fixture(mechanics)
    receipt['action_assessments'][0]['assessment']['max_compression_mm']=3.0
    with pytest.raises(mechanics.MechanicsContractError,match='receipt hash'):
        mechanics.build_feedback_adapted_robot_h_replay_plan(plan,receipt,profile)

    plan,receipt,profile=_arm208_feedback_fixture(mechanics)
    receipt['physical_authority']=True
    receipt['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in receipt.items() if key!='receipt_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='feedback boundary'):
        mechanics.build_feedback_adapted_robot_h_replay_plan(plan,receipt,profile)


def _arm209_trace_fixture(mechanics):
    source,blocked,profile=_arm208_feedback_fixture(mechanics)
    source['joint_targets'][33].update({
        'joint_position_target_rad':[0.0,0.05,0.02,-0.08,0.0,0.0],
        'target_id':'H','action_index':0,
    })
    source['plan_sha256']=mechanics._canonical_sha256({
        key:value for key,value in source.items() if key!='plan_sha256'
    })
    blocked['source_plan_sha256']=source['plan_sha256']
    blocked['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in blocked.items() if key!='receipt_sha256'
    })
    adapted=mechanics.build_feedback_adapted_robot_h_replay_plan(source,blocked,profile)
    receipt={
        'schema':mechanics.FEEDBACK_ADAPTED_ROBOT_H_REPLAY_RECEIPT_SCHEMA,
        'status':'BLOCKED_NATIVE_ROBOT_H_REPLAY',
        'source_plan_sha256':adapted['plan_sha256'],
        'state_teleports_after_initialization':0,
        'action_assessments':[
            {'action_index':0,'assessment':{
                'profile_sha256':profile['profile_sha256'],
                'disposition':'EXCESSIVE_TRAVEL','native_contact_observed':True,
                'activation_count':1,'max_compression_mm':3.78,
                'final_compression_mm':2.36,
            }},
            {'action_index':1,'assessment':{
                'profile_sha256':profile['profile_sha256'],
                'disposition':'EXCESSIVE_TRAVEL','native_contact_observed':True,
                'activation_count':0,'max_compression_mm':3.75,
                'final_compression_mm':2.37,
            }},
        ],
        'native_trace':[
            {'target_sequence':0,'key_center_z_m':0.018,
             'tip_key_separation_m':0.010},
            {'target_sequence':33,'key_center_z_m':0.018,
             'tip_key_separation_m':0.00092},
            {'target_sequence':33,'key_center_z_m':0.01799,
             'tip_key_separation_m':0.00090},
        ],
        'hardware_access':False,'physical_authority':False,'controller_commands':[],
        'hardware_writes':0,'physical_movements':0,'gate_promotions':[],
    }
    receipt['receipt_sha256']=mechanics._canonical_sha256(receipt)
    return adapted,receipt,profile


def test_arm209_trace_lift_reuses_clear_anchor_and_reduces_contact():
    mechanics=_load_key_mechanics()
    source,receipt,profile=_arm209_trace_fixture(mechanics)
    plan=mechanics.build_trace_lifted_robot_h_replay_plan(source,receipt,profile)
    assert plan['status']=='READY_FOR_ZERO_AUTHORITY_TRACE_LIFTED_NATIVE_H_REPLAY'
    lift=plan['trace_lift_adaptation']
    assert lift['no_contact_anchor_sequence']==33
    assert lift['anchor_minimum_clearance_mm']==pytest.approx(0.9)
    assert lift['anchor_maximum_compression_mm']==pytest.approx(0.01)
    assert lift['lifted_hover_retract_sequences']==[34,36,37,39]
    assert lift['contact_interpolation_ratio']==pytest.approx(2.7/3.78)
    anchor=source['joint_targets'][33]['joint_position_target_rad']
    for sequence in (34,36,37,39):
        assert plan['joint_targets'][sequence]['joint_position_target_rad']==anchor
    expected=[
        anchor[index]+(2.7/3.78)*(
            source['joint_targets'][35]['joint_position_target_rad'][index]-anchor[index]
        )
        for index in range(6)
    ]
    assert plan['joint_targets'][35]['joint_position_target_rad']==pytest.approx(expected)
    assert plan['joint_targets'][38]['joint_position_target_rad']==pytest.approx(expected)
    assert lift['adapted_maximum_adjacent_joint_delta_rad'] <= (
        lift['source_maximum_adjacent_joint_delta_rad']
    )
    assert plan['hardware_access'] is False and plan['controller_commands']==[]


def test_arm209_trace_lift_rejects_missing_clearance_and_authority():
    mechanics=_load_key_mechanics()
    source,receipt,profile=_arm209_trace_fixture(mechanics)
    receipt['native_trace'][1]['tip_key_separation_m']=0.0001
    receipt['native_trace'][2]['tip_key_separation_m']=0.0001
    receipt['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in receipt.items() if key!='receipt_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='no-contact anchor'):
        mechanics.build_trace_lifted_robot_h_replay_plan(source,receipt,profile)

    source,receipt,profile=_arm209_trace_fixture(mechanics)
    source['physical_authority']=True
    source['plan_sha256']=mechanics._canonical_sha256({
        key:value for key,value in source.items() if key!='plan_sha256'
    })
    receipt['source_plan_sha256']=source['plan_sha256']
    receipt['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in receipt.items() if key!='receipt_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='trace-lift boundary'):
        mechanics.build_trace_lifted_robot_h_replay_plan(source,receipt,profile)


def _arm210_contact_fixture(mechanics):
    arm208,arm208_receipt,profile=_arm209_trace_fixture(mechanics)
    source=mechanics.build_trace_lifted_robot_h_replay_plan(
        arm208,arm208_receipt,profile
    )
    receipt={
        'schema':mechanics.TRACE_LIFTED_ROBOT_H_REPLAY_RECEIPT_SCHEMA,
        'status':'BLOCKED_NATIVE_ROBOT_H_REPLAY',
        'source_plan_sha256':source['plan_sha256'],
        'state_teleports_after_initialization':0,
        'action_assessments':[
            {'action_index':0,'assessment':{
                'profile_sha256':profile['profile_sha256'],
                'disposition':'EXCESSIVE_TRAVEL','native_contact_observed':True,
                'activation_count':1,'max_compression_mm':3.542,
                'final_compression_mm':0.0,
            }},
            {'action_index':1,'assessment':{
                'profile_sha256':profile['profile_sha256'],
                'disposition':'EXCESSIVE_TRAVEL','native_contact_observed':True,
                'activation_count':1,'max_compression_mm':3.541,
                'final_compression_mm':0.0,
            }},
        ],
        'hardware_access':False,'physical_authority':False,'controller_commands':[],
        'hardware_writes':0,'physical_movements':0,'gate_promotions':[],
    }
    receipt['receipt_sha256']=mechanics._canonical_sha256(receipt)
    return source,receipt,profile


def test_arm210_contact_refinement_preserves_lift_and_changes_only_contacts():
    mechanics=_load_key_mechanics()
    source,receipt,profile=_arm210_contact_fixture(mechanics)
    plan=mechanics.build_contact_refined_robot_h_replay_plan(source,receipt,profile)
    assert plan['status']=='READY_FOR_ZERO_AUTHORITY_CONTACT_REFINED_NATIVE_H_REPLAY'
    refinement=plan['contact_refinement']
    assert refinement['preserved_hover_retract_sequences']==[34,36,37,39]
    assert refinement['adapted_contact_sequences']==[35,38]
    assert refinement['contact_refinement_ratio']==pytest.approx(2.7/3.542)
    anchor=source['joint_targets'][33]['joint_position_target_rad']
    for sequence in (34,36,37,39):
        assert plan['joint_targets'][sequence]==source['joint_targets'][sequence]
        assert plan['joint_targets'][sequence]['joint_position_target_rad']==anchor
    expected=[
        anchor[index]+(2.7/3.542)*(
            source['joint_targets'][35]['joint_position_target_rad'][index]-anchor[index]
        )
        for index in range(6)
    ]
    assert plan['joint_targets'][35]['joint_position_target_rad']==pytest.approx(expected)
    assert all(
        plan['joint_targets'][index]==source['joint_targets'][index]
        for index in range(len(source['joint_targets'])) if index not in (35,38)
    )
    assert plan['hardware_access'] is False and plan['physical_movements']==0


def test_arm210_contact_refinement_rejects_release_or_authority_tampering():
    mechanics=_load_key_mechanics()
    source,receipt,profile=_arm210_contact_fixture(mechanics)
    receipt['action_assessments'][0]['assessment']['final_compression_mm']=1.3
    receipt['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in receipt.items() if key!='receipt_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='contact-only'):
        mechanics.build_contact_refined_robot_h_replay_plan(source,receipt,profile)

    source,receipt,profile=_arm210_contact_fixture(mechanics)
    receipt['hardware_access']=True
    receipt['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in receipt.items() if key!='receipt_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='contact-refinement boundary'):
        mechanics.build_contact_refined_robot_h_replay_plan(source,receipt,profile)


def _arm211_demonstration_fixture(mechanics):
    arm209,arm209_receipt,profile=_arm210_contact_fixture(mechanics)
    plan=mechanics.build_contact_refined_robot_h_replay_plan(
        arm209,arm209_receipt,profile
    )
    sample_count=plan['sample_count']
    assessments=[]
    for action_index,compression in ((0,2.744),(1,2.731)):
        result={
            'accepted':True,'activation_count':1,
            'authority':dict(profile['authority']),'disposition':'ACCEPTED',
            'final_compression_mm':0.0,'max_compression_mm':compression,
            'native_contact_observed':True,'profile_sha256':profile['profile_sha256'],
            'resolved_key':'H',
        }
        result['result_sha256']=mechanics._canonical_sha256(result)
        assessments.append({'action_index':action_index,'assessment':result})
    receipt={
        'schema':mechanics.CONTACT_REFINED_ROBOT_H_REPLAY_RECEIPT_SCHEMA,
        'status':'PASS','source_plan_sha256':plan['plan_sha256'],
        'evidence_class':'PROVISIONAL_NATIVE_DRIVE_CONTROLLED_ROBOT_KEY_CONTACT',
        'state_teleports_after_initialization':0,
        'action_assessments':assessments,
        'root_pose_invariant':{
            'all_passed':True,'observation_count':sample_count,
            'observations':[
                {'sequence':index,'passed':True} for index in range(sample_count)
            ],
        },
        'joint_tracking':[
            {'sequence':index,'maximum_joint_error_rad':0.03}
            for index in range(sample_count)
        ],
        'maximum_joint_tracking_error_rad':0.03,
        'maximum_joint_tracking_error_allowed_rad':0.05,
        'hardware_access':False,'physical_authority':False,'controller_commands':[],
        'hardware_writes':0,'physical_movements':0,'gate_promotions':[],
    }
    receipt['receipt_sha256']=mechanics._canonical_sha256(receipt)
    return plan,receipt,profile


def test_arm211_retains_h_as_governed_adaptation_seed():
    mechanics=_load_key_mechanics()
    plan,receipt,profile=_arm211_demonstration_fixture(mechanics)
    demonstration=mechanics.retain_governed_h_demonstration(plan,receipt,profile)
    assert demonstration['status']=='READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_KEY_ADAPTATION'
    assert demonstration['source_skill']['target_id']=='H'
    assert demonstration['source_skill']['skill_window_sequences']==list(range(33,40))
    assert [
        row['phase'] for row in demonstration['source_skill']['joint_space_samples']
    ]==['TRANSIT','HOVER','CONTACT','RETRACT','HOVER','CONTACT','RETRACT']
    transfer=demonstration['transfer_contract']
    assert transfer['native_qualified_targets']==['H']
    assert transfer['pending_targets']==['1','SPACE','ENTER','PERIOD']
    assert transfer['joint_space_reuse_for_other_keys_permitted'] is False
    assert demonstration['dataset_eligibility']=={
        'eligible_as_skill_adaptation_seed':True,
        'eligible_as_multi_key_dataset':False,
        'eligible_for_physical_execution':False,
    }
    assert demonstration['quality_gate']['accepted_native_action_count']==2
    assert demonstration['quality_gate']['root_pose_observation_count']==plan['sample_count']
    assert demonstration['hardware_access'] is False
    assert demonstration['controller_commands']==[]
    assert demonstration['demonstration_sha256']==mechanics._canonical_sha256({
        key:value for key,value in demonstration.items()
        if key!='demonstration_sha256'
    })


def test_arm211_rejects_tampering_nested_authority_and_failed_quality():
    mechanics=_load_key_mechanics()
    plan,receipt,profile=_arm211_demonstration_fixture(mechanics)
    plan['joint_targets'][35]['joint_position_target_rad'][1]+=0.1
    with pytest.raises(mechanics.MechanicsContractError,match='plan hash'):
        mechanics.retain_governed_h_demonstration(plan,receipt,profile)

    plan,receipt,profile=_arm211_demonstration_fixture(mechanics)
    assessment=receipt['action_assessments'][0]['assessment']
    assessment['authority']['motion']=True
    assessment['result_sha256']=mechanics._canonical_sha256({
        key:value for key,value in assessment.items() if key!='result_sha256'
    })
    receipt['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in receipt.items() if key!='receipt_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='accepted H evidence'):
        mechanics.retain_governed_h_demonstration(plan,receipt,profile)

    plan,receipt,profile=_arm211_demonstration_fixture(mechanics)
    receipt['root_pose_invariant']['observations'][0]['passed']=False
    receipt['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in receipt.items() if key!='receipt_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='quality evidence'):
        mechanics.retain_governed_h_demonstration(plan,receipt,profile)


def _arm212_campaign_fixture(mechanics):
    plan,receipt,profile=_arm211_demonstration_fixture(mechanics)
    demonstration=mechanics.retain_governed_h_demonstration(plan,receipt,profile)
    samples=[]
    for sequence in range(40):
        samples.append({
            'sequence':sequence,'time_from_start_ns':sequence*100_000_000,
            'phase':'TRANSIT','phase_endpoint':False,'action_index':None,
            'target_id':None,'expected_tool_tip_board_mm':[0.0,0.0,30.0],
        })
    samples[0].update({
        'phase':'PARK','phase_endpoint':True,
        'expected_tool_tip_board_mm':[290.0,10.0,70.0],
    })
    for sequence,phase,action in (
        (33,'TRANSIT',0),(34,'HOVER',0),(35,'CONTACT',0),(36,'RETRACT',0),
        (37,'HOVER',1),(38,'CONTACT',1),(39,'RETRACT',1),
    ):
        samples[sequence].update({
            'phase':phase,'phase_endpoint':sequence!=33,'action_index':action,
            'target_id':'H','expected_tool_tip_board_mm':[
                218.71,149.76,27.29
            ],
        })
    source={
        'schema':mechanics.TCP_CARTESIAN_SCHEDULE_SCHEMA,
        'status':'READY_FOR_IK_QUALIFICATION','key_id':'H',
        'profile_sha256':profile['profile_sha256'],'samples':samples,
        'source_joint_positions_reused':False,
        'hardware_access':False,'hardware_writes':0,'physical_movements':0,
        'controller_commands':[],
    }
    source['request_sha256']=mechanics._canonical_sha256(source)
    return demonstration,source,profile


def test_arm212_builds_target_specific_cartesian_requests_without_joint_reuse():
    mechanics=_load_key_mechanics()
    demonstration,source,profile=_arm212_campaign_fixture(mechanics)
    campaign=mechanics.build_representative_key_adaptation_campaign(
        demonstration,source,profile
    )
    assert campaign['status']=='READY_FOR_ZERO_AUTHORITY_TARGET_SPECIFIC_IK_QUALIFICATION'
    assert [row['target_id'] for row in campaign['requests']]==[
        '1','SPACE','ENTER','PERIOD'
    ]
    for request in campaign['requests']:
        assert request['source_joint_positions_reused'] is False
        assert request['route_connection_required'] is True
        contacts=[row for row in request['samples'] if row['phase']=='CONTACT']
        assert len(contacts)==2
        assert all(row['expected_tool_tip_board_mm'][:2]==request['target_center_board_xy_mm'] for row in contacts)
        assert all(row['expected_tool_tip_board_mm'][2]==pytest.approx(18.3) for row in contacts)
    assert campaign['multi_key_dataset_ready'] is False
    assert campaign['physical_movements']==0 and campaign['controller_commands']==[]


def test_arm212_rejects_joint_reuse_or_tampered_demonstration():
    mechanics=_load_key_mechanics()
    demonstration,source,profile=_arm212_campaign_fixture(mechanics)
    source['source_joint_positions_reused']=True
    source['request_sha256']=mechanics._canonical_sha256({
        key:value for key,value in source.items() if key!='request_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='source boundary'):
        mechanics.build_representative_key_adaptation_campaign(
            demonstration,source,profile
        )


def _arm213_campaign_fixture(mechanics):
    demonstration,source,profile=_arm212_campaign_fixture(mechanics)
    adaptation=mechanics.build_representative_key_adaptation_campaign(
        demonstration,source,profile
    )
    route={
        'candidate_id':'route-shape-selected',
        'xy_corridor_topology':'DIRECT_LINEAR',
        'corridor_height_board_mm':90.0,
        'corridor_height_ramp_fraction':0.25,
        'transit_resampling':'ARC_LENGTH_PIECEWISE_LINEAR_WITH_SYMMETRIC_Z_RAMPS',
    }
    selection={
        'schema':mechanics.KEY_MECHANICS_LEARNING_BASELINE_SELECTION_SCHEMA,
        'status':'SELECTED_ZERO_AUTHORITY_SIMULATION_LEARNING_BASELINE',
        'selected_candidate_id':'route-shape-selected',
        'ranked_candidates':[{
            'candidate_id':'route-shape-selected','route_shape_candidate':route,
        }],
        'hardware_access':False,'hardware_writes':0,'physical_movements':0,
        'controller_commands':[],
    }
    selection['selection_sha256']=mechanics._canonical_sha256(selection)
    return adaptation,source,selection,profile


def test_arm213_connects_each_skill_to_park_without_joint_reuse():
    mechanics=_load_key_mechanics()
    adaptation,source,selection,_profile=_arm213_campaign_fixture(mechanics)
    campaign=mechanics.build_representative_key_park_route_campaign(
        adaptation,source,selection
    )
    assert campaign['status']=='READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_ROUTE_IK_QUALIFICATION'
    assert campaign['park_endpoint_board_mm']==[290.0,10.0,70.0]
    assert [request['key_id'] for request in campaign['requests']]==[
        '1','SPACE','ENTER','PERIOD'
    ]
    for source_skill,request in zip(
        adaptation['requests'],campaign['requests'],strict=True
    ):
        assert request['sample_count']==40
        assert request['samples'][0]['expected_tool_tip_board_mm']==[290.0,10.0,70.0]
        assert request['route_domain_sequences']==list(range(1,33))
        assert request['skill_domain_sequences']==list(range(33,40))
        assert [row['expected_tool_tip_board_mm'] for row in request['samples'][33:]]==[
            row['expected_tool_tip_board_mm'] for row in source_skill['samples']
        ]
        assert all(row['expected_tool_tip_board_mm'][2]==90.0 for row in request['samples'][9:25])
        assert request['source_joint_positions_reused'] is False
        assert request['joint_positions_included'] is False
        assert request['hardware_access'] is False and request['controller_commands']==[]


def test_arm213_rejects_tampered_skill_and_route_policy():
    mechanics=_load_key_mechanics()
    adaptation,source,selection,_profile=_arm213_campaign_fixture(mechanics)
    adaptation['requests'][0]['samples'][0]['expected_tool_tip_board_mm'][0]+=1.0
    adaptation['campaign_sha256']=mechanics._canonical_sha256({
        key:value for key,value in adaptation.items() if key!='campaign_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='request hash'):
        mechanics.build_representative_key_park_route_campaign(
            adaptation,source,selection
        )

    adaptation,source,selection,_profile=_arm213_campaign_fixture(mechanics)
    selection['ranked_candidates'][0]['route_shape_candidate'][
        'corridor_height_board_mm'
    ]=70.0
    selection['selection_sha256']=mechanics._canonical_sha256({
        key:value for key,value in selection.items() if key!='selection_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='policy changed'):
        mechanics.build_representative_key_park_route_campaign(
            adaptation,source,selection
        )


def test_arm214_fresh_ik_accepts_all_representative_routes():
    mechanics=_load_key_mechanics()
    adaptation,source,selection,profile=_arm213_campaign_fixture(mechanics)
    routes=mechanics.build_representative_key_park_route_campaign(
        adaptation,source,selection
    )
    bundle=json.loads((
        ROOT/'software/integrations/isaac_sim/evidence/'
        'actual_emitter_joint_schedule_bundle_9e5c878_20260929.json'
    ).read_bytes())
    campaign=mechanics.qualify_representative_key_park_routes_ik(
        routes,source,bundle,profile,workspace=ROOT
    )
    assert campaign['status']=='READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_COLLISION_QUALIFICATION'
    assert campaign['accepted_target_count']==4
    assert campaign['source_h_joint_solutions_reused'] is False
    assert [result['target_id'] for result in campaign['results']]==[
        '1','SPACE','ENTER','PERIOD'
    ]
    assert all(result['ik_all_samples_accepted'] for result in campaign['results'])
    assert all(result['evaluated_sample_count']==40 for result in campaign['results'])
    assert campaign['hardware_access'] is False and campaign['controller_commands']==[]


def test_arm214_rejects_tampered_route_campaign_before_ik():
    mechanics=_load_key_mechanics()
    adaptation,source,selection,profile=_arm213_campaign_fixture(mechanics)
    routes=mechanics.build_representative_key_park_route_campaign(
        adaptation,source,selection
    )
    routes['requests'][0]['samples'][1]['expected_tool_tip_board_mm'][0]+=1.0
    bundle=json.loads((
        ROOT/'software/integrations/isaac_sim/evidence/'
        'actual_emitter_joint_schedule_bundle_9e5c878_20260929.json'
    ).read_bytes())
    with pytest.raises(mechanics.MechanicsContractError,match='campaign hash'):
        mechanics.qualify_representative_key_park_routes_ik(
            routes,source,bundle,profile,workspace=ROOT
        )


def test_arm215_compiles_bounded_fixed_root_replays_and_rejects_tampering():
    mechanics=_load_key_mechanics()
    bundle=json.loads((
        ROOT/'software/integrations/isaac_sim/evidence/'
        'actual_emitter_joint_schedule_bundle_9e5c878_20260929.json'
    ).read_bytes())
    names=list(bundle['samples'][0]['joint_positions_rad'])
    results=[]
    for target_index,target_id in enumerate(('1','SPACE','ENTER','PERIOD')):
        joint_results=[]
        for sequence in range(40):
            endpoint={
                name:bundle['samples'][0]['joint_positions_rad'][name]
                + (target_index+1)*0.002 + sequence*0.001
                for name in names
            }
            joint_results.append({
                'waypoint_sequence':sequence,
                'accepted':True,
                'solution_arm_joint_positions_rad':endpoint,
            })
        result={
            'target_id':target_id,
            'source_request_sha256':str(target_index+1)*64,
            'status':'READY_FOR_COLLISION_AND_FIXED_ROOT_QUALIFICATION',
            'sample_count':40,'evaluated_sample_count':40,
            'ik_all_samples_accepted':True,'joint_results':joint_results,
        }
        result['result_sha256']=mechanics._canonical_sha256(result)
        results.append(result)
    campaign={
        'schema':mechanics.REPRESENTATIVE_KEY_IK_CAMPAIGN_SCHEMA,
        'status':'READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_COLLISION_QUALIFICATION',
        'source_bindings':{
            'canonical_ik_source_bundle_sha256':bundle['bundle_sha256'],
        },
        'source_h_joint_solutions_reused':False,
        'target_count':4,'accepted_target_count':4,'results':results,
        'hardware_access':False,'hardware_writes':0,
        'physical_authority':False,'physical_movements':0,
        'controller_commands':[],'gate_promotions':[],
    }
    campaign['campaign_sha256']=mechanics._canonical_sha256(campaign)
    candidate={
        'schema':'tactevra.simulation_collision_candidate.v1',
        'scope':'SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY',
        'installed':False,'installed_profile_eligible':False,
        'blockers':['exploratory_geometry_is_uninstalled'],
        'robot_bodies':[{'body_id':'robot:base_link'}],
        'workcell_bodies':[{'body_id':'workcell:keyboard'}],
        'hardware_access':False,'physical_authority':False,
        'hardware_write_count':0,'physical_movement_count':0,'commands':[],
    }
    candidate['candidate_sha256']=mechanics._canonical_sha256(candidate)
    toolchain=json.loads((
        ROOT/'software/config/isaac_sim_toolchain_lock.json'
    ).read_bytes())

    compiled=mechanics.build_representative_key_collision_replay_campaign(
        campaign,bundle,candidate,toolchain
    )
    assert compiled['status']==(
        'READY_FOR_ZERO_AUTHORITY_FIXED_ROOT_NATIVE_COLLISION_REPLAY'
    )
    assert compiled['target_count']==4
    assert [row['target_id'] for row in compiled['target_plans']]==[
        '1','SPACE','ENTER','PERIOD'
    ]
    assert all(40 <= row['bounded_sample_count'] <= 256
               for row in compiled['target_plans'])
    assert all(row['fixed_base_contract']['mechanism']=='USD_FIXED_JOINT_TO_WORLD'
               for row in compiled['target_plans'])
    assert all(row['root_pose_invariant']['required_after_every_sample'] is True
               for row in compiled['target_plans'])
    assert compiled['native_replay_executed'] is False
    assert compiled['installed_collision_qualified'] is False
    assert compiled['hardware_access'] is False
    assert compiled['controller_commands']==[]

    campaign['results'][0]['joint_results'][1][
        'solution_arm_joint_positions_rad'
    ][names[0]]+=0.1
    campaign['campaign_sha256']=mechanics._canonical_sha256({
        key:value for key,value in campaign.items() if key!='campaign_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='result hash'):
        mechanics.build_representative_key_collision_replay_campaign(
            campaign,bundle,candidate,toolchain
        )


def test_arm216_materializes_and_aggregates_representative_native_admissions(
    tmp_path,
):
    mechanics=_load_key_mechanics()
    adaptation,source,selection,profile=_arm213_campaign_fixture(mechanics)
    routes=mechanics.build_representative_key_park_route_campaign(
        adaptation,source,selection
    )
    bundle=json.loads((
        ROOT/'software/integrations/isaac_sim/evidence/'
        'actual_emitter_joint_schedule_bundle_9e5c878_20260929.json'
    ).read_bytes())
    seed=bundle['samples'][0]['joint_positions_rad']
    results=[]
    for target_index,(target_id,request) in enumerate(zip(
        ('1','SPACE','ENTER','PERIOD'),routes['requests'],strict=True
    )):
        joint_results=[]
        for sequence in range(40):
            sample=request['samples'][sequence]
            joint_results.append({
                'waypoint_sequence':sequence,
                'accepted':True,
                'phase':sample['phase'],
                'action_index':sample['action_index'],
                'semantic_target':sample.get('target_id'),
                'solution_arm_joint_positions_rad':{
                    name:value+(target_index+1)*0.002+sequence*0.001
                    for name,value in seed.items()
                },
            })
        result={
            'target_id':target_id,
            'source_request_sha256':request['request_sha256'],
            'status':'READY_FOR_COLLISION_AND_FIXED_ROOT_QUALIFICATION',
            'sample_count':40,'evaluated_sample_count':40,
            'ik_all_samples_accepted':True,'joint_results':joint_results,
        }
        result['result_sha256']=mechanics._canonical_sha256(result)
        results.append(result)
    placement=[
        1.0,0.0,0.0,385.0,
        0.0,1.0,0.0,532.0,
        0.0,0.0,1.0,70.1,
        0.0,0.0,0.0,1.0,
    ]
    virtual_bytes=json.dumps({
        'study_input':{'physical_placement_input':{'matrix_row_major':placement}}
    },sort_keys=True).encode()
    ik_campaign={
        'schema':mechanics.REPRESENTATIVE_KEY_IK_CAMPAIGN_SCHEMA,
        'status':'READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_COLLISION_QUALIFICATION',
        'source_bindings':{
            'arm213_route_campaign_sha256':routes['campaign_sha256'],
            'canonical_ik_source_bundle_sha256':bundle['bundle_sha256'],
            'virtual_profile_sha256':hashlib.sha256(virtual_bytes).hexdigest(),
            'key_mechanics_profile_sha256':profile['profile_sha256'],
        },
        'source_h_joint_solutions_reused':False,
        'target_count':4,'accepted_target_count':4,'results':results,
        'hardware_access':False,'physical_authority':False,
        'hardware_writes':0,'physical_movements':0,
        'controller_commands':[],'gate_promotions':[],
    }
    ik_campaign['campaign_sha256']=mechanics._canonical_sha256(ik_campaign)
    identity=[1.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,1.0]
    def body(body_id,center,half):
        return {'body_id':body_id,'parent_frame':'board','primitives':[{
            'kind':'oriented_box','center_mm':center,'half_extents_mm':half,
            'rotation_row_major':identity,
        }]}
    candidate={
        'schema':'tactevra.simulation_collision_candidate.v1',
        'scope':'SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY',
        'status':'EXPLORATORY_UNINSTALLED_COLLISION_CANDIDATE_FAMILY',
        'installed':False,'installed_profile_eligible':False,
        'blockers':['exploratory_geometry_is_uninstalled'],
        'robot_bodies':[{'body_id':'robot:base_link'}],
        'workcell_bodies':[
            body('workcell:board_solid',[305.0,228.5,-9.0],[305.0,228.5,9.0]),
            body('workcell:keyboard',[242.5,158.5,10.5],[157.5,73.5,10.5]),
            body('workcell:phone',[538.15,166.4,7.95],[38.95,82.2,3.95]),
            body('workcell:station:keyboard_left',[172.25,168.0,17.5],[92.25,96.0,17.5]),
            body('workcell:station:keyboard_right',[323.75,168.0,17.5],[81.25,96.0,17.5]),
        ],
        'hardware_access':False,'physical_authority':False,
        'hardware_write_count':0,'physical_movement_count':0,'commands':[],
    }
    candidate['candidate_sha256']=mechanics._canonical_sha256(candidate)
    toolchain=json.loads((
        ROOT/'software/config/isaac_sim_toolchain_lock.json'
    ).read_bytes())
    collision=mechanics.build_representative_key_collision_replay_campaign(
        ik_campaign,bundle,candidate,toolchain
    )
    policy={
        'schema':mechanics.TCP_COLLISION_POLICY_SCHEMA,
        'status':'ACCEPTED_FOR_ZERO_AUTHORITY_DIAGNOSTIC_ONLY',
        'collision_candidate_sha256':candidate['candidate_sha256'],
        'diagnostic_policy_active':True,'installed_profile_active':False,
        'installed_profile_eligible':False,'accepted_exclusion_count':0,
        'accepted_exclusions':[],'physical_solid_pairs_excluded':[],
        'planning_envelope_pairs_excluded':[],'gate_promotions':[],
        'hardware_access':False,'physical_authority':False,
        'hardware_writes':0,'physical_movements':0,'controller_commands':[],
    }
    policy['policy_sha256']=mechanics._canonical_sha256(policy)
    manifest=mechanics.materialize_representative_key_native_collision_inputs(
        routes,ik_campaign,collision,bundle,candidate,toolchain,policy,
        output_dir=tmp_path,
    )
    assert [row['station_region_id'] for row in manifest['entries']]==[
        'workcell:station:keyboard_left','workcell:station:keyboard_left',
        'workcell:station:keyboard_right','workcell:station:keyboard_right',
    ]
    assert all((tmp_path/row['directory']/'fixed_base_replay_plan.json').is_file()
               for row in manifest['entries'])

    receipts=[]
    for entry in manifest['entries']:
        receipt={
            'schema':mechanics.REPRESENTATIVE_KEY_NATIVE_COLLISION_RECEIPT_SCHEMA,
            'status':'DIAGNOSTIC_OVERLAPS_OBSERVED',
            'representative_target_id':entry['target_id'],
            'source_arm215_campaign_sha256':collision['campaign_sha256'],
            'source_arm215_target_plan_sha256':entry[
                'source_arm215_target_plan_sha256'
            ],
            'source_representative_plan_mutated':False,
            'bounded_sample_count':entry['bounded_sample_count'],
            'unique_collision_pair_count':5,'policy_excluded_pair_count':5,
            'physical_solid_blocker_pair_count':0,
            'planning_envelope_blocker_pair_count':0,
            'unreviewed_blocker_pair_count':0,
            'root_pose_invariant':{
                'status':'PASS',
                'observation_count':entry['bounded_sample_count']+1,
            },
            'hardware_access':False,'physical_authority':False,
            'hardware_writes':0,'physical_movements':0,'controller_commands':[],
        }
        receipt['receipt_sha256']=mechanics._canonical_sha256(receipt)
        receipts.append(receipt)
    campaign=mechanics.aggregate_representative_key_native_collision_campaign(
        manifest,receipts
    )
    assert campaign['status']==(
        'PASS_REPRESENTATIVE_ZERO_AUTHORITY_NATIVE_COLLISION_CAMPAIGN'
    )
    assert campaign['total_bounded_sample_count']==sum(
        row['bounded_sample_count'] for row in manifest['entries']
    )
    assert campaign['fixed_root_invariant_passed'] is True
    assert campaign['installed_collision_qualified'] is False

    drive_path=ROOT/'software/config/isaac_lm0b_geometry_prior_profile.json'
    drive_bytes=drive_path.read_bytes()
    drive=json.loads(drive_bytes)
    robot_bytes=b'#usda 1.0\n'
    joint_order=[
        'base_link_to_link1','link1_to_link2','link2_to_link3',
        'link3_to_link4','link4_to_link5','link5_to_gripper_link',
    ]
    import_receipt={
        'schema':'tactevra.isaac_sim_urdf_import.v1',
        'external_files':[{
            'sha256':hashlib.sha256(robot_bytes).hexdigest(),
            'size_bytes':len(robot_bytes),
        }],
        'articulation_root_normalization':{
            'expected_live_dof_order':joint_order,
        },
    }
    import_receipt['receipt_sha256']=mechanics._canonical_sha256(import_receipt)
    mechanics_campaign=mechanics.build_representative_key_native_mechanics_campaign(
        routes,ik_campaign,manifest,receipts,profile,virtual_bytes,
        drive,drive_bytes,robot_bytes,import_receipt,
    )
    assert mechanics_campaign['status']==(
        'READY_FOR_ZERO_AUTHORITY_REPRESENTATIVE_NATIVE_MECHANICS_REPLAY'
    )
    assert [plan['target_id'] for plan in mechanics_campaign['plans']]==[
        '1','SPACE','ENTER','PERIOD'
    ]
    assert all(plan['sample_count']==40 for plan in mechanics_campaign['plans'])
    assert all(
        len(plan['contact_endpoint_sequences'])==2
        for plan in mechanics_campaign['plans']
    )
    assert mechanics_campaign['native_mechanics_replay_executed'] is False
    assert mechanics_campaign['hardware_access'] is False

    mechanics_receipts=[]
    for plan in mechanics_campaign['plans']:
        target_id=plan['target_id']
        action_assessments=[{
            'action_index':action_index,
            'assessment':{
                'accepted':True,'resolved_key':target_id,
                'commanded_key':target_id,'native_contact_observed':True,
            },
        } for action_index in (0,1)]
        receipt={
            'schema':mechanics.REPRESENTATIVE_KEY_NATIVE_MECHANICS_RECEIPT_SCHEMA,
            'status':'PASS','target_id':target_id,
            'source_plan_sha256':plan['plan_sha256'],
            'source_arm216_receipt_sha256':plan['source_bindings'][
                'arm216_receipt_sha256'
            ],
            'state_teleports_after_initialization':0,
            'action_assessments':action_assessments,
            'maximum_joint_tracking_error_rad':0.01,
            'maximum_joint_tracking_error_allowed_rad':0.05,
            'root_pose_invariant':{
                'all_passed':True,'observation_count':plan['sample_count'],
            },
            'native_trace':[{'time_s':0.0},{'time_s':0.01}],
            'hardware_access':False,'physical_authority':False,
            'hardware_writes':0,'physical_movements':0,'controller_commands':[],
        }
        receipt['receipt_sha256']=mechanics._canonical_sha256(receipt)
        mechanics_receipts.append(receipt)
    mechanics_result=(
        mechanics.aggregate_representative_key_native_mechanics_campaign(
            mechanics_campaign,mechanics_receipts
        )
    )
    assert mechanics_result['status']==(
        'PASS_REPRESENTATIVE_ZERO_AUTHORITY_NATIVE_MECHANICS_CAMPAIGN'
    )
    assert mechanics_result['accepted_action_count']==8
    assert mechanics_result['multi_key_dataset_ready'] is True
    assert mechanics_result['physical_keyboard_qualified'] is False

    blocked_receipts=[]
    for plan in mechanics_campaign['plans']:
        target_id=plan['target_id']
        action_assessments=[{
            'action_index':action_index,
            'assessment':{
                'accepted':False,'resolved_key':target_id,
                'commanded_key':target_id,'native_contact_observed':True,
                'profile_sha256':profile['profile_sha256'],
                'disposition':'EXCESSIVE_TRAVEL',
                'activation_count':1 if action_index==0 else 0,
                'max_compression_mm':3.7,
                'final_compression_mm':2.1,
            },
        } for action_index in (0,1)]
        receipt={
            'schema':mechanics.REPRESENTATIVE_KEY_NATIVE_MECHANICS_RECEIPT_SCHEMA,
            'status':'BLOCKED_REPRESENTATIVE_NATIVE_KEY_MECHANICS_REPLAY',
            'target_id':target_id,
            'source_plan_sha256':plan['plan_sha256'],
            'source_arm216_receipt_sha256':plan['source_bindings'][
                'arm216_receipt_sha256'
            ],
            'state_teleports_after_initialization':0,
            'action_assessments':action_assessments,
            'maximum_joint_tracking_error_rad':0.04,
            'maximum_joint_tracking_error_allowed_rad':0.05,
            'root_pose_invariant':{
                'all_passed':True,'observation_count':plan['sample_count'],
            },
            'native_trace':[
                {
                    'target_sequence':32,'key_center_z_m':0.018,
                    'tip_key_separation_m':0.001,
                },
                {
                    'target_sequence':35,'key_center_z_m':0.0143,
                    'tip_key_separation_m':-0.001,
                },
            ],
            'hardware_access':False,'physical_authority':False,
            'hardware_writes':0,'physical_movements':0,
            'controller_commands':[],'gate_promotions':[],
        }
        receipt['receipt_sha256']=mechanics._canonical_sha256(receipt)
        blocked_receipts.append(receipt)
    adapted_campaign=(
        mechanics.build_feedback_adapted_representative_key_mechanics_campaign(
            mechanics_campaign,blocked_receipts,profile
        )
    )
    assert adapted_campaign['status']==(
        'READY_FOR_ZERO_AUTHORITY_FEEDBACK_ADAPTED_MECHANICS_REPLAY'
    )
    assert [plan['target_id'] for plan in adapted_campaign['plans']]==[
        '1','SPACE','ENTER','PERIOD'
    ]
    assert all(
        plan['feedback_adaptation']['release_anchor_sequence']==32
        and plan['feedback_adaptation']['mechanics_thresholds_changed'] is False
        and plan['feedback_adaptation']['target_region_changed'] is False
        and plan['hardware_access'] is False
        for plan in adapted_campaign['plans']
    )
    bad_blocked=json.loads(json.dumps(blocked_receipts))
    bad_blocked[0]['native_trace'][0]['tip_key_separation_m']=-0.001
    bad_blocked[0]['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in bad_blocked[0].items()
        if key!='receipt_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='released anchor'):
        mechanics.build_feedback_adapted_representative_key_mechanics_campaign(
            mechanics_campaign,bad_blocked,profile
        )

    adapted_receipts=[]
    for plan in adapted_campaign['plans']:
        target_id=plan['target_id']
        passed=target_id=='ENTER'
        action_assessments=[{
            'action_index':action_index,
            'assessment':{
                'accepted':passed,'resolved_key':target_id,
                'commanded_key':target_id,'native_contact_observed':True,
                'profile_sha256':profile['profile_sha256'],
                'disposition':'ACCEPTED' if passed else 'EXCESSIVE_TRAVEL',
                'activation_count':1,'max_compression_mm':3.25 if passed else 3.6,
                'final_compression_mm':0.0,
            },
        } for action_index in (0,1)]
        receipt={
            'schema':mechanics.REPRESENTATIVE_KEY_NATIVE_MECHANICS_RECEIPT_SCHEMA,
            'status':'PASS' if passed else (
                'BLOCKED_REPRESENTATIVE_NATIVE_KEY_MECHANICS_REPLAY'
            ),
            'target_id':target_id,'source_plan_sha256':plan['plan_sha256'],
            'state_teleports_after_initialization':0,
            'action_assessments':action_assessments,
            'maximum_joint_tracking_error_rad':0.04,
            'root_pose_invariant':{
                'all_passed':True,'observation_count':plan['sample_count'],
            },
            'hardware_access':False,'physical_authority':False,
            'hardware_writes':0,'physical_movements':0,
            'controller_commands':[],'gate_promotions':[],
        }
        receipt['receipt_sha256']=mechanics._canonical_sha256(receipt)
        adapted_receipts.append(receipt)
    refined_campaign=(
        mechanics.build_contact_refined_representative_key_mechanics_campaign(
            adapted_campaign,adapted_receipts,profile
        )
    )
    assert refined_campaign['preserved_passing_targets']==['ENTER']
    assert refined_campaign['contact_refined_targets']==['1','SPACE','PERIOD']
    enter_index=refined_campaign['preserved_passing_targets'].index('ENTER')
    assert refined_campaign['plans'][2]['plan_sha256']==(
        adapted_campaign['plans'][2]['plan_sha256']
    )
    assert enter_index==0
    assert all(
        plan['contact_refinement']['mechanics_thresholds_changed'] is False
        for plan in refined_campaign['plans'] if plan['target_id']!='ENTER'
    )

    mechanics_receipts[0]['maximum_joint_tracking_error_rad']=0.06
    mechanics_receipts[0]['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in mechanics_receipts[0].items()
        if key!='receipt_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='boundary changed'):
        mechanics.aggregate_representative_key_native_mechanics_campaign(
            mechanics_campaign,mechanics_receipts
        )

    receipts[0]['root_pose_invariant']['status']='FAIL'
    receipts[0]['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in receipts[0].items() if key!='receipt_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='boundary changed'):
        mechanics.build_representative_key_native_mechanics_campaign(
            routes,ik_campaign,manifest,receipts,profile,virtual_bytes,
            drive,drive_bytes,robot_bytes,import_receipt,
        )

    receipts[0]['root_pose_invariant']['status']='PASS'
    receipts[0]['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in receipts[0].items() if key!='receipt_sha256'
    })
    receipts[0]['physical_solid_blocker_pair_count']=1
    receipts[0]['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in receipts[0].items() if key!='receipt_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='boundary changed'):
        mechanics.aggregate_representative_key_native_collision_campaign(
            manifest,receipts
        )

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


@pytest.fixture
def arm218_contract():
    mechanics=_load_key_mechanics()
    def signed(value,field):
        value[field]=mechanics._canonical_sha256(value)
        return value
    plans={}
    receipts={}
    results=[]
    for target in mechanics.REPRESENTATIVE_KEYS[1:]:
        plans[target]=signed({
            'schema':'test.plan.v1','target_id':target,'hardware_access':False,
            'physical_authority':False,'controller_commands':[],
        },'plan_sha256')
        receipts[target]=signed({
            'schema':'test.receipt.v1','target_id':target,'hardware_access':False,
            'hardware_writes':0,'physical_authority':False,
            'physical_movements':0,'controller_commands':[],
        },'receipt_sha256')
        results.append({
            'target_id':target,'plan_sha256':plans[target]['plan_sha256'],
            'receipt_sha256':receipts[target]['receipt_sha256'],
            'native_trace_sample_count':1416,'root_pose_invariant_passed':True,
        })
    source=signed({
        'schema':mechanics.REPRESENTATIVE_KEY_NATIVE_MECHANICS_RESULT_CAMPAIGN_SCHEMA,
        'status':'PASS_REPRESENTATIVE_ZERO_AUTHORITY_NATIVE_MECHANICS_CAMPAIGN',
        'results':results,'hardware_access':False,'hardware_writes':0,
        'physical_authority':False,'physical_movements':0,
        'controller_commands':[],'gate_promotions':[],
    },'campaign_sha256')
    return mechanics,source,plans,receipts


def _arm218_receipts(mechanics,campaign):
    receipts={}
    for index,episode in enumerate(campaign['episodes']):
        failed=index in {5,19}
        value={
            'schema':mechanics.RANDOMIZED_DEMONSTRATION_EPISODE_RECEIPT_SCHEMA,
            'source_campaign_sha256':campaign['campaign_sha256'],
            'episode_id':episode['episode_id'],'partition':episode['partition'],
            'seed':episode['seed'],'scene_id':episode['scene_id'],
            'target_id':episode['target_id'],
            'parameter_region':episode['parameter_region'],
            'randomized_parameters':episode['randomized_parameters'],
            'source_plan_sha256':episode['source_plan_sha256'],
            'source_receipt_sha256':episode['source_receipt_sha256'],
            'complete':True,'disposition':'FAIL' if failed else 'PASS',
            'failure_reason':'TRACKING_ERROR' if failed else None,
            'trajectory_sha256':f'{index:064x}','hardware_access':False,
            'hardware_writes':0,'physical_authority':False,
            'physical_movements':0,'controller_commands':[],'gate_promotions':[],
        }
        value['receipt_sha256']=mechanics._canonical_sha256(value)
        receipts[episode['episode_id']]=value
    return receipts


def _arm219_dataset_inputs(mechanics,source,plans,source_receipts):
    campaign=mechanics.build_randomized_demonstration_campaign(
        source,plans,source_receipts,master_seed=218
    )
    receipts=_arm218_receipts(mechanics,campaign)
    trajectories={}
    for index,episode in enumerate(campaign['episodes']):
        row={
            'schema':mechanics.STATE_POLICY_TRAJECTORY_SCHEMA,
            'time_s':0.01,
            'target_id':episode['target_id'],
            'phase':'CONTACT',
            'action_index':0,
            'target_sequence':1,
            'joint_position_observed_rad':[index+joint/10 for joint in range(6)],
            'joint_velocity_observed_rad_s':[joint/100 for joint in range(6)],
            'joint_position_target_rad':[index+joint/20 for joint in range(6)],
            'key_center_z_m':0.01,
            'tip_center_z_m':0.02,
            'tip_key_separation_m':0.001,
        }
        payload=(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode()
        trajectories[episode['episode_id']]=payload
        receipt=receipts[episode['episode_id']]
        receipt.update({
            'trajectory_schema':mechanics.STATE_POLICY_TRAJECTORY_SCHEMA,
            'joint_order':['j1','j2','j3','j4','j5','j6'],
            'native_trace_sample_count':1,
            'randomized_key_center_board_xy_mm':[1.0,2.0],
            'trajectory_sha256':hashlib.sha256(payload).hexdigest(),
        })
        receipt['receipt_sha256']=mechanics._canonical_sha256({
            key:value for key,value in receipt.items() if key!='receipt_sha256'
        })
    result=mechanics.aggregate_randomized_demonstration_campaign(
        campaign,receipts
    )
    return campaign,result,receipts,trajectories


def test_arm218_campaign_is_deterministic_disjoint_and_balanced(arm218_contract):
    mechanics,source,plans,receipts=arm218_contract
    first=mechanics.build_randomized_demonstration_campaign(
        source,plans,receipts,master_seed=218
    )
    second=mechanics.build_randomized_demonstration_campaign(
        source,plans,receipts,master_seed=218
    )
    assert first==second
    assert first['partition_counts']=={'train':12,'validation':8,'test':4}
    assert first['attempted_episode_count']==24
    assert len({item['seed'] for item in first['episodes']})==24
    assert len({item['scene_id'] for item in first['episodes']})==24
    assert {item['target_id'] for item in first['episodes']}==set(
        mechanics.REPRESENTATIVE_KEYS[1:]
    )
    assert first['hardware_access'] is first['physical_authority'] is False
    mechanics.validate_randomized_demonstration_campaign(first)


def test_arm218_campaign_rejects_tampered_lineage_and_authority(arm218_contract):
    mechanics,source,plans,receipts=arm218_contract
    tampered=json.loads(json.dumps(source))
    tampered['results'][0]['receipt_sha256']='0'*64
    tampered['campaign_sha256']=mechanics._canonical_sha256({
        key:value for key,value in tampered.items() if key!='campaign_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='binding mismatch'):
        mechanics.build_randomized_demonstration_campaign(
            tampered,plans,receipts,master_seed=218
        )
    plans['1']['physical_authority']=True
    plans['1']['plan_sha256']=mechanics._canonical_sha256({
        key:value for key,value in plans['1'].items() if key!='plan_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='zero-authority'):
        mechanics.build_randomized_demonstration_campaign(
            source,plans,receipts,master_seed=218
        )


def test_arm218_aggregate_retains_failures_and_denominator(arm218_contract):
    mechanics,source,plans,source_receipts=arm218_contract
    campaign=mechanics.build_randomized_demonstration_campaign(
        source,plans,source_receipts,master_seed=218
    )
    result=mechanics.aggregate_randomized_demonstration_campaign(
        campaign,_arm218_receipts(mechanics,campaign)
    )
    assert result['attempted_episode_count']==result['completed_episode_count']==24
    assert result['passed_episode_count']==22
    assert result['failed_episode_count']==2
    assert result['failure_counts_by_reason']=={'TRACKING_ERROR':2}
    assert len(result['retained_episodes'])==24


def test_arm218_aggregate_rejects_incomplete_or_filtered_shards(arm218_contract):
    mechanics,source,plans,source_receipts=arm218_contract
    campaign=mechanics.build_randomized_demonstration_campaign(
        source,plans,source_receipts,master_seed=218
    )
    receipts=_arm218_receipts(mechanics,campaign)
    receipts.pop(next(iter(receipts)))
    with pytest.raises(mechanics.MechanicsContractError,match='attempted denominator'):
        mechanics.aggregate_randomized_demonstration_campaign(campaign,receipts)
    receipts=_arm218_receipts(mechanics,campaign)
    key=next(iter(receipts))
    receipts[key]['complete']=False
    receipts[key]['receipt_sha256']=mechanics._canonical_sha256({
        field:value for field,value in receipts[key].items()
        if field!='receipt_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='incomplete'):
        mechanics.aggregate_randomized_demonstration_campaign(campaign,receipts)


def test_arm218_aggregate_rejects_partition_relabeling(arm218_contract):
    mechanics,source,plans,source_receipts=arm218_contract
    campaign=mechanics.build_randomized_demonstration_campaign(
        source,plans,source_receipts,master_seed=218
    )
    receipts=_arm218_receipts(mechanics,campaign)
    key=next(iter(receipts))
    receipts[key]['partition']='test'
    receipts[key]['receipt_sha256']=mechanics._canonical_sha256({
        field:value for field,value in receipts[key].items()
        if field!='receipt_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='partition'):
        mechanics.aggregate_randomized_demonstration_campaign(campaign,receipts)


def test_arm219_dataset_manifest_is_deterministic_and_leakage_safe(
    arm218_contract,
):
    mechanics,source,plans,source_receipts=arm218_contract
    inputs=_arm219_dataset_inputs(mechanics,source,plans,source_receipts)
    first=mechanics.build_state_policy_dataset_manifest(*inputs)
    second=mechanics.build_state_policy_dataset_manifest(*inputs)
    assert first==second
    assert first['schema']==mechanics.STATE_POLICY_DATASET_MANIFEST_SCHEMA
    assert first['attempted_episode_count']==first['total_row_count']==24
    assert first['role_counts']=={
        'EVALUATION':11,'REJECTION_EVIDENCE':2,'TRAINING':11,
    }
    assert first['normalization']['source_partition']=='train'
    assert first['normalization']['sample_count']==first['training_row_count']==11
    assert len(first['feature_contract']['numeric_inputs'])==23
    assert len(first['normalization']['statistics'])==23
    assert all(
        set(episode['randomized_parameters'])==set(
            inputs[0]['randomization_contract']['ranges']
        )
        and len(episode['randomized_key_center_board_xy_mm'])==2
        for episode in first['episodes']
    )
    assert all(
        episode['role']=='TRAINING'
        for episode in first['episodes']
        if episode['role']=='TRAINING'
    )
    assert all(
        episode['partition']=='train' and episode['disposition']=='PASS'
        for episode in first['episodes']
        if episode['role']=='TRAINING'
    )
    assert all(
        episode['role']=='REJECTION_EVIDENCE'
        for episode in first['episodes']
        if episode['disposition']=='FAIL'
    )
    assert first['hardware_access'] is first['physical_authority'] is False


def test_arm219_dataset_manifest_rejects_tampered_trajectory(arm218_contract):
    mechanics,source,plans,source_receipts=arm218_contract
    campaign,result,receipts,trajectories=_arm219_dataset_inputs(
        mechanics,source,plans,source_receipts
    )
    episode_id=campaign['episodes'][0]['episode_id']
    trajectories[episode_id]+=b'{}\n'
    with pytest.raises(mechanics.MechanicsContractError,match='digest'):
        mechanics.build_state_policy_dataset_manifest(
            campaign,result,receipts,trajectories
        )


def test_arm219_dataset_manifest_rejects_schema_and_joint_order_drift(
    arm218_contract,
):
    mechanics,source,plans,source_receipts=arm218_contract
    campaign,result,receipts,trajectories=_arm219_dataset_inputs(
        mechanics,source,plans,source_receipts
    )
    episode_id=campaign['episodes'][0]['episode_id']
    receipts[episode_id]['joint_order']=['wrong']*6
    receipts[episode_id]['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in receipts[episode_id].items()
        if key!='receipt_sha256'
    })
    result=mechanics.aggregate_randomized_demonstration_campaign(
        campaign,receipts
    )
    with pytest.raises(mechanics.MechanicsContractError,match='joint order'):
        mechanics.build_state_policy_dataset_manifest(
            campaign,result,receipts,trajectories
        )


def test_arm219_state_policy_baseline_is_deterministic_and_partitioned(
    arm218_contract,
):
    mechanics,source,plans,source_receipts=arm218_contract
    campaign,result,receipts,trajectories=_arm219_dataset_inputs(
        mechanics,source,plans,source_receipts
    )
    manifest=mechanics.build_state_policy_dataset_manifest(
        campaign,result,receipts,trajectories
    )
    first=mechanics.fit_state_policy_baseline(manifest,trajectories)
    second=mechanics.fit_state_policy_baseline(manifest,trajectories)
    assert first==second
    assert first['schema']==mechanics.STATE_POLICY_BASELINE_SCHEMA
    assert first['source_dataset_sha256']==manifest['dataset_sha256']
    assert first['hyperparameters']=={
        'ridge_lambda':0.001,'random_seed':None,'stochastic_operations':False,
    }
    assert first['metrics']['training']['sample_count']==11
    assert first['metrics']['held_out_evaluation']['sample_count']==11
    assert first['metrics']['rejection_evidence_sample_count']==2
    assert len(first['feature_encoding']['encoded_features'])==36
    assert len(first['weights_by_output_joint'])==6
    assert all(len(weights)==36 for weights in first['weights_by_output_joint'])
    assert first['proposal_replay_status']=='NOT_RUN'
    assert first['hardware_access'] is first['physical_authority'] is False


def test_arm219_state_policy_baseline_rejects_tampered_inputs(arm218_contract):
    mechanics,source,plans,source_receipts=arm218_contract
    campaign,result,receipts,trajectories=_arm219_dataset_inputs(
        mechanics,source,plans,source_receipts
    )
    manifest=mechanics.build_state_policy_dataset_manifest(
        campaign,result,receipts,trajectories
    )
    episode_id=campaign['episodes'][0]['episode_id']
    trajectories[episode_id]+=b'{}\n'
    with pytest.raises(mechanics.MechanicsContractError,match='digest'):
        mechanics.fit_state_policy_baseline(manifest,trajectories)
    with pytest.raises(mechanics.MechanicsContractError,match='positive'):
        mechanics.fit_state_policy_baseline(
            manifest,{key:value for key,value in trajectories.items() if key!=episode_id}
            | {episode_id:trajectories[episode_id][:-3]},ridge_lambda=0.0
        )


def test_arm219_proposal_replay_campaign_is_deterministic_and_held_out(
    arm218_contract,
):
    mechanics,source,plans,source_receipts=arm218_contract
    campaign,result,receipts,trajectories=_arm219_dataset_inputs(
        mechanics,source,plans,source_receipts
    )
    manifest=mechanics.build_state_policy_dataset_manifest(
        campaign,result,receipts,trajectories
    )
    model=mechanics.fit_state_policy_baseline(manifest,trajectories)
    evaluation_ids={
        episode['episode_id'] for episode in manifest['episodes']
        if episode['role']=='EVALUATION'
    }
    evaluation={key:trajectories[key] for key in evaluation_ids}
    first,first_payloads=mechanics.build_state_policy_proposal_replay_campaign(
        manifest,model,evaluation
    )
    second,second_payloads=mechanics.build_state_policy_proposal_replay_campaign(
        manifest,model,evaluation
    )
    assert first==second
    assert first_payloads==second_payloads
    assert first['schema']==mechanics.STATE_POLICY_PROPOSAL_REPLAY_CAMPAIGN_SCHEMA
    assert first['held_out_episode_count']==11
    assert first['proposal_sample_count']==11
    assert set(first_payloads)==evaluation_ids
    assert all(
        hashlib.sha256(first_payloads[episode['episode_id']]).hexdigest()
        ==episode['proposal_trajectory_sha256']
        for episode in first['episodes']
    )
    assert first['required_replay_gates']==[
        'FIXED_ROOT','JOINT_TRACKING','COLLISION','CONTACT','RELEASE','SETTLING',
    ]
    assert first['continuity_diagnostic'][
        'requires_bounded_collision_interpolation'
    ] is False
    assert first['hardware_access'] is first['physical_authority'] is False


def test_arm219_proposal_replay_campaign_rejects_training_or_tampered_rows(
    arm218_contract,
):
    mechanics,source,plans,source_receipts=arm218_contract
    campaign,result,receipts,trajectories=_arm219_dataset_inputs(
        mechanics,source,plans,source_receipts
    )
    manifest=mechanics.build_state_policy_dataset_manifest(
        campaign,result,receipts,trajectories
    )
    model=mechanics.fit_state_policy_baseline(manifest,trajectories)
    evaluation_ids={
        episode['episode_id'] for episode in manifest['episodes']
        if episode['role']=='EVALUATION'
    }
    evaluation={key:trajectories[key] for key in evaluation_ids}
    evaluation[next(iter(evaluation_ids))]+=b'{}\n'
    with pytest.raises(mechanics.MechanicsContractError,match='digest'):
        mechanics.build_state_policy_proposal_replay_campaign(
            manifest,model,evaluation
        )
    training_id=next(
        episode['episode_id'] for episode in manifest['episodes']
        if episode['role']=='TRAINING'
    )
    evaluation[training_id]=trajectories[training_id]
    with pytest.raises(mechanics.MechanicsContractError,match='held-out'):
        mechanics.build_state_policy_proposal_replay_campaign(
            manifest,model,evaluation
        )


def test_arm219_proposal_continuity_blocks_large_adjacent_steps(arm218_contract):
    mechanics,*_=arm218_contract
    rows=[
        {
            'phase':'HOVER','target_sequence':34,
            'joint_position_proposal_rad':[0.0]*6,
        },
        {
            'phase':'CONTACT','target_sequence':35,
            'joint_position_proposal_rad':[0.0,0.0,0.051,0.0,0.0,0.0],
        },
    ]
    result=mechanics._state_policy_proposal_continuity(rows)
    assert result['violation_count']==1
    assert result['maximum_observed_adjacent_joint_step_rad']==pytest.approx(0.051)
    assert result['violations'][0]['left_phase']=='HOVER'
    assert result['violations'][0]['right_phase']=='CONTACT'


def _arm219_collision_sources(mechanics,proposal_campaign):
    targets={episode['target_id'] for episode in proposal_campaign['episodes']}
    inputs={}
    results=[]
    for index,target in enumerate(sorted(targets)):
        collision={
            'schema':mechanics.TCP_POLICY_BOUND_COLLISION_REQUEST_SCHEMA,
            'status':'READY_FOR_ZERO_AUTHORITY_COLLISION_DIAGNOSTIC',
            'source_request_sha256':str(index+1)*64,
            'collision_candidate_sha256':'c'*64,
            'collision_pair_policy_sha256':'p'*64,
            'toolchain_lock_sha256':'t'*64,
            'hardware_access':False,'hardware_writes':0,
            'physical_authority':False,'physical_movements':0,
            'controller_commands':[],'gate_promotions':[],
        }
        collision['request_sha256']=mechanics._canonical_sha256(collision)
        fixed={
            'schema':mechanics.REPRESENTATIVE_KEY_NATIVE_COLLISION_REPLAY_PLAN_SCHEMA,
            'status':'READY_FOR_FIXED_BASE_ZERO_AUTHORITY_NATIVE_REPLAY',
            'target_id':target,
            'source_collision_request_sha256':collision['request_sha256'],
            'source_arm215_target_plan_sha256':str(index+5)*64,
            'hardware_access':False,'hardware_writes':0,
            'physical_authority':False,'physical_movements':0,
            'controller_commands':[],'gate_promotions':[],
        }
        fixed['plan_sha256']=mechanics._canonical_sha256(fixed)
        predicate={
            'schema':mechanics.STATION_ROUTE_PREDICATE_SCHEMA,'status':'PASS',
            'source_cartesian_request_sha256':collision['source_request_sha256'],
            'hardware_access':False,'hardware_writes':0,
            'physical_authority':False,'physical_movements':0,
            'controller_commands':[],'gate_promotions':[],
        }
        predicate['predicate_sha256']=mechanics._canonical_sha256(predicate)
        inputs[target]={
            'collision_request':collision,
            'fixed_base_replay_plan':fixed,
            'station_route_predicate':predicate,
        }
        results.append({
            'target_id':target,
            'source_arm215_target_plan_sha256':fixed[
                'source_arm215_target_plan_sha256'
            ],
        })
    campaign={
        'schema':mechanics.REPRESENTATIVE_KEY_NATIVE_COLLISION_CAMPAIGN_SCHEMA,
        'status':'PASS_REPRESENTATIVE_ZERO_AUTHORITY_NATIVE_COLLISION_CAMPAIGN',
        'results':results,
        'hardware_access':False,'hardware_writes':0,
        'physical_authority':False,'physical_movements':0,
        'controller_commands':[],'gate_promotions':[],
    }
    campaign['campaign_sha256']=mechanics._canonical_sha256(campaign)
    return campaign,inputs


def _arm219_runtime_admission_sources(mechanics,proposal_campaign,runtime_hashes=None):
    native,inputs=_arm219_collision_sources(mechanics,proposal_campaign)
    entries=[]
    common=runtime_hashes or {
        'virtual_profile_sha256':'v'*64,
        'robot_import_receipt_sha256':'i'*64,
        'robot_usd_sha256':'u'*64,
        'toolchain_lock_sha256':'t'*64,
    }
    for target,target_inputs in inputs.items():
        collision=target_inputs['collision_request']
        fixed=target_inputs['fixed_base_replay_plan']
        predicate=target_inputs['station_route_predicate']
        if runtime_hashes is not None:
            collision['toolchain_lock_sha256']=common['toolchain_lock_sha256']
            collision['request_sha256']=mechanics._canonical_sha256({
                key:value for key,value in collision.items()
                if key!='request_sha256'
            })
            fixed['source_collision_request_sha256']=collision['request_sha256']
            fixed['plan_sha256']=mechanics._canonical_sha256({
                key:value for key,value in fixed.items() if key!='plan_sha256'
            })
        receipt={
            'schema':mechanics.REPRESENTATIVE_KEY_NATIVE_COLLISION_RECEIPT_SCHEMA,
            'status':'DIAGNOSTIC_OVERLAPS_OBSERVED',
            'representative_target_id':target,
            'collision_screening_executed':True,
            'fixed_base_replay_applied':True,
            'root_pose_invariant':{'status':'PASS'},
            'source_bindings':{
                'request_sha256':collision['request_sha256'],
                'fixed_base_replay_plan_sha256':fixed['plan_sha256'],
                'station_route_predicate_sha256':predicate['predicate_sha256'],
                'collision_candidate_sha256':collision[
                    'collision_candidate_sha256'
                ],
                'collision_pair_policy_sha256':collision[
                    'collision_pair_policy_sha256'
                ],
                **common,
            },
            'hardware_access':False,'hardware_writes':0,
            'physical_authority':False,'physical_movements':0,
            'controller_commands':[],'gate_promotions':[],
        }
        receipt['receipt_sha256']=mechanics._canonical_sha256(receipt)
        target_inputs['native_receipt']=receipt
        entries.append({
            'target_id':target,'directory':target.lower(),
            'source_arm215_target_plan_sha256':fixed[
                'source_arm215_target_plan_sha256'
            ],
            'document_hashes':{
                'collision_request.json':collision['request_sha256'],
                'fixed_base_replay_plan.json':fixed['plan_sha256'],
                'station_route_predicate.json':predicate['predicate_sha256'],
            },
        })
        result=next(row for row in native['results'] if row['target_id']==target)
        result.update({
            'receipt_sha256':receipt['receipt_sha256'],
            'unreviewed_blocker_pair_count':0,
            'physical_solid_blocker_pair_count':0,
            'planning_envelope_blocker_pair_count':0,
        })
    manifest={
        'schema':mechanics.REPRESENTATIVE_KEY_NATIVE_COLLISION_MANIFEST_SCHEMA,
        'status':'READY_FOR_SELECTED_ZERO_AUTHORITY_NATIVE_REPLAY',
        'entries':entries,
        'hardware_access':False,'hardware_writes':0,
        'physical_authority':False,'physical_movements':0,
        'controller_commands':[],'gate_promotions':[],
    }
    manifest['manifest_sha256']=mechanics._canonical_sha256(manifest)
    native['source_manifest_sha256']=manifest['manifest_sha256']
    native['campaign_sha256']=mechanics._canonical_sha256({
        key:value for key,value in native.items() if key!='campaign_sha256'
    })
    return manifest,native,inputs


def _arm219_runtime_files(mechanics):
    virtual_bytes=json.dumps({
        'schema':'rocell.virtual_commissioning_profile.v1',
        'status':'UNMEASURED_SENSITIVITY_OVERLAY',
        'simulation_only':True,
        'physical_release_effect':'NONE',
    },sort_keys=True).encode()
    robot_usd=b'#usda 1.0\ndef Xform "robot" {}\n'
    import_receipt={
        'schema':'tactevra.isaac_sim_urdf_import.v1',
        'external_files':[{
            'path':'robot.usda',
            'sha256':hashlib.sha256(robot_usd).hexdigest(),
            'size_bytes':len(robot_usd),
        }],
        'hardware_access':False,'hardware_writes':0,
        'physical_authority':False,'physical_movements':0,
        'wire_commands':[],
    }
    import_receipt['receipt_sha256']=mechanics._canonical_sha256(import_receipt)
    toolchain={
        'schema':'rocell.isaac_sim_toolchain_lock.v1',
        'selection_status':'SELECTED',
        'hardware_access':False,
        'physical_authority':False,
        'wire_commands':[],
    }
    hashes={
        'virtual_profile_sha256':hashlib.sha256(virtual_bytes).hexdigest(),
        'robot_import_receipt_sha256':import_receipt['receipt_sha256'],
        'robot_usd_sha256':hashlib.sha256(robot_usd).hexdigest(),
        'toolchain_lock_sha256':mechanics._canonical_sha256(toolchain),
    }
    return virtual_bytes,import_receipt,robot_usd,toolchain,hashes


def _arm219_native_start_sources(arm218_contract):
    mechanics,source,plans,source_receipts=arm218_contract
    campaign,result,receipts,trajectories=_arm219_dataset_inputs(
        mechanics,source,plans,source_receipts
    )
    dataset=mechanics.build_state_policy_dataset_manifest(
        campaign,result,receipts,trajectories
    )
    model=mechanics.fit_state_policy_baseline(dataset,trajectories)
    evaluation={
        episode['episode_id']:trajectories[episode['episode_id']]
        for episode in dataset['episodes'] if episode['role']=='EVALUATION'
    }
    proposal,payloads=mechanics.build_state_policy_proposal_replay_campaign(
        dataset,model,evaluation
    )
    virtual,import_receipt,usd,toolchain,hashes=_arm219_runtime_files(mechanics)
    native_manifest,native,native_inputs=_arm219_runtime_admission_sources(
        mechanics,proposal,hashes
    )
    request_campaign,requests=mechanics.build_state_policy_collision_request_campaign(
        proposal,payloads,native,native_inputs
    )
    admission,admissions=mechanics.admit_state_policy_collision_request_campaign(
        dataset,model,proposal,request_campaign,requests,
        native_manifest,native,native_inputs
    )
    revalidation,revalidations=(
        mechanics.revalidate_state_policy_collision_runtime_inputs(
            admission,admissions,virtual,import_receipt,usd,toolchain
        )
    )
    return mechanics,revalidation,revalidations,requests,native_inputs


def _arm220_complete_collision_sources(arm218_contract):
    mechanics,revalidation,revalidations,requests,native_inputs=(
        _arm219_native_start_sources(arm218_contract)
    )
    manifest,bundles=mechanics.materialize_state_policy_native_collision_inputs(
        revalidation,revalidations,requests,native_inputs
    )
    accepted_pairs=[
        ['robot:base_link','robot:link1'],
        ['robot:gripper','robot:link5'],
        ['robot:link1','robot:link2'],
        ['robot:link2','robot:link3'],
        ['robot:link3','robot:link4'],
    ]
    native_receipts={}
    for entry in manifest['entries']:
        samples=[]
        for sequence in range(entry['bounded_sample_count']):
            samples.append({
                'sample_id':f'proposal-sample-{sequence:04d}',
                'sample_sequence':sequence,
                'raw_collision_pair_count':5,
                'raw_collision_pairs':accepted_pairs,
                'policy_excluded_pair_count':5,
                'policy_excluded_pairs':accepted_pairs,
                'physical_solid_blocker_pairs':[],
                'planning_envelope_blocker_pairs':[],
                'unreviewed_blocker_pairs':[],
                'remaining_blocker_pair_count':0,
            })
        receipt={
            'schema':mechanics.STATE_POLICY_NATIVE_COLLISION_RECEIPT_SCHEMA,
            'status':'DIAGNOSTIC_OVERLAPS_OBSERVED',
            'state_policy_episode_id':entry['episode_id'],
            'state_policy_target_id':entry['target_id'],
            'source_state_policy_request_sha256':(
                entry['state_policy_request_sha256']
            ),
            'source_runtime_revalidation_receipt_sha256':(
                entry['runtime_revalidation_receipt_sha256']
            ),
            'source_bindings':{
                'request_sha256':entry['native_collision_request_sha256'],
                'fixed_base_replay_plan_sha256':(
                    entry['native_fixed_base_replay_plan_sha256']
                ),
            },
            'bounded_sample_count':entry['bounded_sample_count'],
            'samples_with_overlaps':entry['bounded_sample_count'],
            'unique_collision_pair_count':5,
            'policy_excluded_pair_count':5,
            'physical_solid_blocker_pair_count':0,
            'planning_envelope_blocker_pair_count':0,
            'unreviewed_blocker_pair_count':0,
            'pair_observations':[
                {
                    'body_pair':pair,
                    'classification':(
                        'ACCEPTED_DIAGNOSTIC_KINEMATIC_NEIGHBOR_EXCLUSION'
                    ),
                    'persistent_across_all_samples':True,
                    'sample_count':entry['bounded_sample_count'],
                }
                for pair in accepted_pairs
            ],
            'samples':samples,
            'collision_screening_executed':True,
            'fixed_base_replay_applied':True,
            'root_pose_invariant':{
                'status':'PASS',
                'maximum_translation_delta_mm':0.01,
                'maximum_orientation_delta_deg':0.06,
                'translation_tolerance_mm':0.05,
                'orientation_tolerance_deg':0.1,
            },
            'hardware_access':False,'hardware_writes':0,
            'physical_authority':False,'physical_movements':0,
            'controller_commands':[],'gate_promotions':[],
        }
        receipt['receipt_sha256']=mechanics._canonical_sha256(receipt)
        native_receipts[entry['episode_id']]=receipt
    campaign=mechanics.aggregate_state_policy_native_collision_campaign(
        manifest,native_receipts
    )
    return mechanics,manifest,campaign,native_receipts


def test_arm219_collision_samples_interpolate_jumps_and_preserve_phase():
    mechanics=_load_key_mechanics()
    rows=[]
    for index,(phase,value) in enumerate((
        ('HOVER',0.0),('HOVER',0.01),('CONTACT',0.12),('CONTACT',0.13),
    )):
        rows.append({
            'schema':mechanics.STATE_POLICY_PROPOSAL_ROW_SCHEMA,
            'phase':phase,
            'joint_position_proposal_rad':[0.0,value,0.0,0.0,0.0,0.0],
        })
    samples,summary=mechanics._state_policy_bounded_collision_samples(rows)
    assert summary['source_sample_count']==4
    assert summary['interpolated_sample_count']==2
    assert summary['preserved_phase_boundary_count']==1
    assert summary['maximum_observed_bounded_joint_step_rad']<=0.05
    assert samples[0]['source_left_row_index']==0
    assert samples[-1]['source_right_row_index']==3
    assert [sample['sample_sequence'] for sample in samples]==list(range(len(samples)))


def test_arm219_collision_request_campaign_is_bound_and_deterministic(
    arm218_contract,
):
    mechanics,source,plans,source_receipts=arm218_contract
    campaign,result,receipts,trajectories=_arm219_dataset_inputs(
        mechanics,source,plans,source_receipts
    )
    manifest=mechanics.build_state_policy_dataset_manifest(
        campaign,result,receipts,trajectories
    )
    model=mechanics.fit_state_policy_baseline(manifest,trajectories)
    evaluation={
        episode['episode_id']:trajectories[episode['episode_id']]
        for episode in manifest['episodes'] if episode['role']=='EVALUATION'
    }
    proposal,proposal_payloads=mechanics.build_state_policy_proposal_replay_campaign(
        manifest,model,evaluation
    )
    native,native_inputs=_arm219_collision_sources(mechanics,proposal)
    first,first_requests=mechanics.build_state_policy_collision_request_campaign(
        proposal,proposal_payloads,native,native_inputs
    )
    second,second_requests=mechanics.build_state_policy_collision_request_campaign(
        proposal,proposal_payloads,native,native_inputs
    )
    assert first==second and first_requests==second_requests
    assert first['schema']==mechanics.STATE_POLICY_COLLISION_REQUEST_CAMPAIGN_SCHEMA
    assert first['episode_count']==proposal['held_out_episode_count']
    assert first['prior_collision_results_reused'] is False
    assert first['fresh_collision_diagnostics_required']==first['episode_count']
    assert first['hardware_access'] is first['physical_authority'] is False
    assert set(first_requests)==set(evaluation)
    for request in first_requests.values():
        assert request['schema']==mechanics.STATE_POLICY_COLLISION_REQUEST_SCHEMA
        assert request['prior_collision_result_reused'] is False
        assert request['fresh_collision_diagnostic_required'] is True
        assert request['bounded_sample_count']<=256
        assert request['bounded_sampling_policy'][
            'maximum_observed_bounded_joint_step_rad'
        ]<=0.05


def test_arm219_collision_request_campaign_rejects_tampered_proposal(
    arm218_contract,
):
    mechanics,source,plans,source_receipts=arm218_contract
    campaign,result,receipts,trajectories=_arm219_dataset_inputs(
        mechanics,source,plans,source_receipts
    )
    manifest=mechanics.build_state_policy_dataset_manifest(
        campaign,result,receipts,trajectories
    )
    model=mechanics.fit_state_policy_baseline(manifest,trajectories)
    evaluation={
        episode['episode_id']:trajectories[episode['episode_id']]
        for episode in manifest['episodes'] if episode['role']=='EVALUATION'
    }
    proposal,payloads=mechanics.build_state_policy_proposal_replay_campaign(
        manifest,model,evaluation
    )
    native,native_inputs=_arm219_collision_sources(mechanics,proposal)
    episode_id=next(iter(payloads))
    payloads[episode_id]+=b'{}\n'
    with pytest.raises(mechanics.MechanicsContractError,match='digest'):
        mechanics.build_state_policy_collision_request_campaign(
            proposal,payloads,native,native_inputs
        )


def test_arm219_collision_runtime_admission_is_deterministic_and_stops_early(
    arm218_contract,
):
    mechanics,source,plans,source_receipts=arm218_contract
    campaign,result,receipts,trajectories=_arm219_dataset_inputs(
        mechanics,source,plans,source_receipts
    )
    dataset=mechanics.build_state_policy_dataset_manifest(
        campaign,result,receipts,trajectories
    )
    model=mechanics.fit_state_policy_baseline(dataset,trajectories)
    evaluation={
        episode['episode_id']:trajectories[episode['episode_id']]
        for episode in dataset['episodes'] if episode['role']=='EVALUATION'
    }
    proposal,payloads=mechanics.build_state_policy_proposal_replay_campaign(
        dataset,model,evaluation
    )
    native_manifest,native,native_inputs=_arm219_runtime_admission_sources(
        mechanics,proposal
    )
    request_campaign,requests=mechanics.build_state_policy_collision_request_campaign(
        proposal,payloads,native,native_inputs
    )
    first,first_admissions=mechanics.admit_state_policy_collision_request_campaign(
        dataset,model,proposal,request_campaign,requests,
        native_manifest,native,native_inputs
    )
    second,second_admissions=mechanics.admit_state_policy_collision_request_campaign(
        dataset,model,proposal,request_campaign,requests,
        native_manifest,native,native_inputs
    )
    assert first==second and first_admissions==second_admissions
    assert first['schema']==(
        mechanics.STATE_POLICY_COLLISION_RUNTIME_ADMISSION_CAMPAIGN_SCHEMA
    )
    assert first['admission_count']==request_campaign['episode_count']
    assert first['total_bounded_sample_count']==(
        request_campaign['total_bounded_sample_count']
    )
    assert first['runtime_files_revalidated'] is False
    assert first['isaac_started'] is first['gpu_started'] is False
    assert first['collision_diagnostics_executed']==0
    assert first['fresh_collision_diagnostics_required']==first['admission_count']
    assert set(first_admissions)==set(requests)
    for admission in first_admissions.values():
        assert admission['runtime_files_revalidated'] is False
        assert admission['collision_diagnostic_executed'] is False
        assert admission['prior_collision_result_reused'] is False
        assert admission['hardware_access'] is admission['physical_authority'] is False


def test_arm219_collision_runtime_admission_rejects_tampered_model(
    arm218_contract,
):
    mechanics,source,plans,source_receipts=arm218_contract
    campaign,result,receipts,trajectories=_arm219_dataset_inputs(
        mechanics,source,plans,source_receipts
    )
    dataset=mechanics.build_state_policy_dataset_manifest(
        campaign,result,receipts,trajectories
    )
    model=mechanics.fit_state_policy_baseline(dataset,trajectories)
    evaluation={
        episode['episode_id']:trajectories[episode['episode_id']]
        for episode in dataset['episodes'] if episode['role']=='EVALUATION'
    }
    proposal,payloads=mechanics.build_state_policy_proposal_replay_campaign(
        dataset,model,evaluation
    )
    native_manifest,native,native_inputs=_arm219_runtime_admission_sources(
        mechanics,proposal
    )
    request_campaign,requests=mechanics.build_state_policy_collision_request_campaign(
        proposal,payloads,native,native_inputs
    )
    model['weights_by_output_joint'][0][0]+=0.001
    with pytest.raises(mechanics.MechanicsContractError,match='model_sha256'):
        mechanics.admit_state_policy_collision_request_campaign(
            dataset,model,proposal,request_campaign,requests,
            native_manifest,native,native_inputs
        )


def test_arm219_runtime_revalidation_is_deterministic_and_stops_before_isaac(
    arm218_contract,
):
    mechanics,source,plans,source_receipts=arm218_contract
    campaign,result,receipts,trajectories=_arm219_dataset_inputs(
        mechanics,source,plans,source_receipts
    )
    dataset=mechanics.build_state_policy_dataset_manifest(
        campaign,result,receipts,trajectories
    )
    model=mechanics.fit_state_policy_baseline(dataset,trajectories)
    evaluation={
        episode['episode_id']:trajectories[episode['episode_id']]
        for episode in dataset['episodes'] if episode['role']=='EVALUATION'
    }
    proposal,payloads=mechanics.build_state_policy_proposal_replay_campaign(
        dataset,model,evaluation
    )
    virtual,import_receipt,usd,toolchain,hashes=_arm219_runtime_files(mechanics)
    native_manifest,native,native_inputs=_arm219_runtime_admission_sources(
        mechanics,proposal,hashes
    )
    request_campaign,requests=mechanics.build_state_policy_collision_request_campaign(
        proposal,payloads,native,native_inputs
    )
    admission,admissions=mechanics.admit_state_policy_collision_request_campaign(
        dataset,model,proposal,request_campaign,requests,
        native_manifest,native,native_inputs
    )
    first,first_receipts=mechanics.revalidate_state_policy_collision_runtime_inputs(
        admission,admissions,virtual,import_receipt,usd,toolchain
    )
    second,second_receipts=mechanics.revalidate_state_policy_collision_runtime_inputs(
        admission,admissions,virtual,import_receipt,usd,toolchain
    )
    assert first==second and first_receipts==second_receipts
    assert first['schema']==(
        mechanics.STATE_POLICY_COLLISION_RUNTIME_REVALIDATION_CAMPAIGN_SCHEMA
    )
    assert first['runtime_files_revalidated'] is True
    assert first['revalidated_file_count']==4
    assert first['isaac_started'] is first['gpu_started'] is False
    assert first['collision_diagnostics_executed']==0
    assert first['fresh_collision_diagnostics_required']==len(admissions)
    assert first['runtime_files']['virtual_profile']['hash_mode']=='RAW_FILE_BYTES'
    assert first['runtime_files']['toolchain_lock']['hash_mode']==(
        'CANONICAL_JSON_DOCUMENT'
    )
    assert set(first_receipts)==set(admissions)
    for receipt in first_receipts.values():
        assert receipt['runtime_files_revalidated'] is True
        assert receipt['collision_diagnostic_executed'] is False
        assert receipt['hardware_access'] is receipt['physical_authority'] is False


def test_arm219_runtime_revalidation_rejects_changed_runtime_files(
    arm218_contract,
):
    mechanics,source,plans,source_receipts=arm218_contract
    campaign,result,receipts,trajectories=_arm219_dataset_inputs(
        mechanics,source,plans,source_receipts
    )
    dataset=mechanics.build_state_policy_dataset_manifest(
        campaign,result,receipts,trajectories
    )
    model=mechanics.fit_state_policy_baseline(dataset,trajectories)
    evaluation={
        episode['episode_id']:trajectories[episode['episode_id']]
        for episode in dataset['episodes'] if episode['role']=='EVALUATION'
    }
    proposal,payloads=mechanics.build_state_policy_proposal_replay_campaign(
        dataset,model,evaluation
    )
    virtual,import_receipt,usd,toolchain,hashes=_arm219_runtime_files(mechanics)
    native_manifest,native,native_inputs=_arm219_runtime_admission_sources(
        mechanics,proposal,hashes
    )
    request_campaign,requests=mechanics.build_state_policy_collision_request_campaign(
        proposal,payloads,native,native_inputs
    )
    admission,admissions=mechanics.admit_state_policy_collision_request_campaign(
        dataset,model,proposal,request_campaign,requests,
        native_manifest,native,native_inputs
    )
    with pytest.raises(mechanics.MechanicsContractError,match='robot USD'):
        mechanics.revalidate_state_policy_collision_runtime_inputs(
            admission,admissions,virtual,import_receipt,usd+b'changed',toolchain
        )
    changed_toolchain=dict(toolchain,isaac_sim_version='changed')
    with pytest.raises(mechanics.MechanicsContractError,match='toolchain_lock_sha256'):
        mechanics.revalidate_state_policy_collision_runtime_inputs(
            admission,admissions,virtual,import_receipt,usd,changed_toolchain
        )


def test_arm220_native_inputs_preserve_complete_lm4_denominator(arm218_contract):
    mechanics,revalidation,revalidations,requests,native_inputs=(
        _arm219_native_start_sources(arm218_contract)
    )
    first,first_bundles=mechanics.materialize_state_policy_native_collision_inputs(
        revalidation,revalidations,requests,native_inputs
    )
    second,second_bundles=mechanics.materialize_state_policy_native_collision_inputs(
        revalidation,revalidations,requests,native_inputs
    )
    assert first==second and first_bundles==second_bundles
    assert first['schema']==mechanics.STATE_POLICY_NATIVE_COLLISION_MANIFEST_SCHEMA
    assert first['episode_count']==len(requests)
    assert first['total_bounded_sample_count']==(
        revalidation['total_bounded_sample_count']
    )
    assert first['isaac_started'] is first['gpu_started'] is False
    assert first['collision_diagnostics_executed']==0
    assert set(first_bundles)==set(requests)
    for episode_id,bundle in first_bundles.items():
        request=bundle['collision_request']
        plan=bundle['fixed_base_replay_plan']
        assert request['source_state_policy_request_sha256']==(
            requests[episode_id]['request_sha256']
        )
        assert request['bounded_sample_count']==len(request['bounded_samples'])
        assert all('source_segment_index' in row for row in request['bounded_samples'])
        assert plan['schema']==mechanics.STATE_POLICY_NATIVE_COLLISION_REPLAY_PLAN_SCHEMA
        assert plan['source_collision_request_sha256']==request['request_sha256']
        assert plan['source_bounded_sample_count']==request['bounded_sample_count']


def test_arm220_native_inputs_reject_changed_revalidation(arm218_contract):
    mechanics,revalidation,revalidations,requests,native_inputs=(
        _arm219_native_start_sources(arm218_contract)
    )
    episode_id=next(iter(revalidations))
    revalidations[episode_id]['bounded_sample_count']+=1
    revalidations[episode_id]['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in revalidations[episode_id].items()
        if key!='receipt_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='lineage|samples'):
        mechanics.materialize_state_policy_native_collision_inputs(
            revalidation,revalidations,requests,native_inputs
        )


def test_arm220_native_campaign_aggregates_only_complete_receipts(arm218_contract):
    mechanics,revalidation,revalidations,requests,native_inputs=(
        _arm219_native_start_sources(arm218_contract)
    )
    manifest,bundles=mechanics.materialize_state_policy_native_collision_inputs(
        revalidation,revalidations,requests,native_inputs
    )
    native_receipts={}
    for entry in manifest['entries']:
        receipt={
            'schema':mechanics.STATE_POLICY_NATIVE_COLLISION_RECEIPT_SCHEMA,
            'status':'DIAGNOSTIC_NO_OVERLAPS_OBSERVED',
            'state_policy_episode_id':entry['episode_id'],
            'state_policy_target_id':entry['target_id'],
            'source_state_policy_request_sha256':(
                entry['state_policy_request_sha256']
            ),
            'source_runtime_revalidation_receipt_sha256':(
                entry['runtime_revalidation_receipt_sha256']
            ),
            'source_bindings':{
                'request_sha256':entry['native_collision_request_sha256'],
                'fixed_base_replay_plan_sha256':(
                    entry['native_fixed_base_replay_plan_sha256']
                ),
            },
            'bounded_sample_count':entry['bounded_sample_count'],
            'samples_with_overlaps':0,
            'unique_collision_pair_count':0,
            'policy_excluded_pair_count':0,
            'physical_solid_blocker_pair_count':0,
            'planning_envelope_blocker_pair_count':0,
            'unreviewed_blocker_pair_count':0,
            'collision_screening_executed':True,
            'fixed_base_replay_applied':True,
            'root_pose_invariant':{
                'status':'PASS',
                'maximum_translation_delta_mm':0.0,
                'maximum_orientation_delta_deg':0.0,
                'translation_tolerance_mm':0.05,
                'orientation_tolerance_deg':0.1,
            },
            'hardware_access':False,'hardware_writes':0,
            'physical_authority':False,'physical_movements':0,
            'controller_commands':[],'gate_promotions':[],
        }
        receipt['receipt_sha256']=mechanics._canonical_sha256(receipt)
        native_receipts[entry['episode_id']]=receipt
    result=mechanics.aggregate_state_policy_native_collision_campaign(
        manifest,native_receipts
    )
    assert result['schema']==mechanics.STATE_POLICY_NATIVE_COLLISION_CAMPAIGN_SCHEMA
    assert result['collision_diagnostics_executed']==manifest['episode_count']
    assert result['total_bounded_sample_count']==(
        manifest['total_bounded_sample_count']
    )
    assert result['isaac_started'] is result['gpu_started'] is True
    assert result['hardware_access'] is result['physical_authority'] is False
    native_receipts.pop(next(iter(native_receipts)))
    with pytest.raises(mechanics.MechanicsContractError,match='denominator'):
        mechanics.aggregate_state_policy_native_collision_campaign(
            manifest,native_receipts
        )


def test_arm221_collision_review_accepts_only_mechanics_plan_compilation(
    arm218_contract,
):
    mechanics,manifest,campaign,receipts=(
        _arm220_complete_collision_sources(arm218_contract)
    )
    first=mechanics.review_state_policy_native_collision_campaign(
        campaign,manifest,receipts
    )
    second=mechanics.review_state_policy_native_collision_campaign(
        campaign,manifest,receipts
    )
    assert first==second
    assert first['schema']==mechanics.STATE_POLICY_NATIVE_COLLISION_REVIEW_SCHEMA
    assert first['status']==(
        'ACCEPTED_FOR_ZERO_AUTHORITY_MECHANICS_PLAN_COMPILATION'
    )
    assert first['episode_count']==manifest['episode_count']
    assert first['total_bounded_sample_count']==(
        manifest['total_bounded_sample_count']
    )
    assert first['review_decision']['mechanics_plan_compilation_allowed'] is True
    assert first['review_decision']['mechanics_replay_execution_authorized'] is False
    assert first['mechanics_replay_executed'] is False
    assert first['native_replay_authorized'] is False
    assert first['hardware_access'] is first['physical_authority'] is False
    assert first['next_required_stage']==(
        'COMPILE_LM4_ZERO_AUTHORITY_MECHANICS_REPLAY_PLANS'
    )


def test_arm221_collision_review_rejects_changed_pair_disposition(arm218_contract):
    mechanics,manifest,campaign,receipts=(
        _arm220_complete_collision_sources(arm218_contract)
    )
    episode_id=next(iter(receipts))
    receipts[episode_id]['samples'][0]['policy_excluded_pairs']=(
        receipts[episode_id]['samples'][0]['policy_excluded_pairs'][:-1]
    )
    receipts[episode_id]['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in receipts[episode_id].items()
        if key!='receipt_sha256'
    })
    campaign=mechanics.aggregate_state_policy_native_collision_campaign(
        manifest,receipts
    )
    with pytest.raises(mechanics.MechanicsContractError,match='sample 0 changed'):
        mechanics.review_state_policy_native_collision_campaign(
            campaign,manifest,receipts
        )


def test_arm221_collision_review_rejects_incomplete_denominator(arm218_contract):
    mechanics,manifest,campaign,receipts=(
        _arm220_complete_collision_sources(arm218_contract)
    )
    receipts.pop(next(iter(receipts)))
    with pytest.raises(mechanics.MechanicsContractError,match='denominator'):
        mechanics.review_state_policy_native_collision_campaign(
            campaign,manifest,receipts
        )


def test_arm218_rejects_undeclared_or_out_of_range_parameters(arm218_contract):
    mechanics,source,plans,receipts=arm218_contract
    campaign=mechanics.build_randomized_demonstration_campaign(
        source,plans,receipts,master_seed=218
    )
    campaign['episodes'][0]['randomized_parameters']['hidden_parameter']=1.0
    campaign['campaign_sha256']=mechanics._canonical_sha256({
        key:value for key,value in campaign.items() if key!='campaign_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='declared'):
        mechanics.validate_randomized_demonstration_campaign(campaign)
    campaign=mechanics.build_randomized_demonstration_campaign(
        source,plans,receipts,master_seed=218
    )
    campaign['episodes'][0]['randomized_parameters']['key_stiffness_n_per_m']=700.0
    campaign['campaign_sha256']=mechanics._canonical_sha256({
        key:value for key,value in campaign.items() if key!='campaign_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='outside'):
        mechanics.validate_randomized_demonstration_campaign(campaign)


def test_arm218_keyboard_pose_transform_is_deterministic(arm218_contract):
    mechanics,*_=arm218_contract
    point=mechanics._randomized_keyboard_point_mm(
        [10.0,0.0],offset_x_mm=1.0,offset_y_mm=-2.0,yaw_deg=90.0
    )
    assert point==pytest.approx([1.0,8.0])


def test_arm219_state_policy_row_binds_observation_action_and_phase(
    arm218_contract,
):
    mechanics,*_=arm218_contract
    target={
        'action_index':0,'sequence':7,'phase':'CONTACT','target_id':'1',
        'joint_position_target_rad':[0.1,0.2,0.3,0.4,0.5,0.6],
    }
    row=mechanics._state_policy_trajectory_row(
        time_s=0.125,target=target,
        observed_joint_positions_rad=[0.11,0.21,0.31,0.41,0.51,0.61],
        observed_joint_velocities_rad_s=[1.0,2.0,3.0,4.0,5.0,6.0],
        key_center_z_m=0.018,tip_center_z_m=0.021,
        tip_key_separation_m=0.001,
    )
    assert row['schema']==mechanics.STATE_POLICY_TRAJECTORY_SCHEMA
    assert row['phase']=='CONTACT'
    assert row['target_id']=='1'
    assert row['target_sequence']==7
    assert row['joint_position_target_rad']==target['joint_position_target_rad']
    assert row['joint_position_observed_rad'][0]==pytest.approx(0.11)
    assert row['joint_velocity_observed_rad_s'][-1]==pytest.approx(6.0)


def test_arm219_state_policy_row_rejects_incomplete_joint_state(arm218_contract):
    mechanics,*_=arm218_contract
    with pytest.raises(mechanics.MechanicsContractError,match='six commanded'):
        mechanics._state_policy_trajectory_row(
            time_s=0.125,
            target={
                'action_index':0,'sequence':7,'phase':'CONTACT','target_id':'1',
                'joint_position_target_rad':[0.1]*6,
            },
            observed_joint_positions_rad=[0.1]*5,
            observed_joint_velocities_rad_s=[0.0]*6,
            key_center_z_m=0.018,tip_center_z_m=0.021,
            tip_key_separation_m=0.001,
        )


def test_arm218_episode_worker_retains_trace_and_complete_receipt(
    arm218_contract,tmp_path,monkeypatch
):
    mechanics,source,plans,source_receipts=arm218_contract
    campaign=mechanics.build_randomized_demonstration_campaign(
        source,plans,source_receipts,master_seed=218
    )
    episode=campaign['episodes'][0]
    target=episode['target_id']
    source_receipt=dict(source_receipts[target])
    source_receipt['source_plan_sha256']=plans[target]['plan_sha256']
    source_receipt['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in source_receipt.items()
        if key!='receipt_sha256'
    })
    episode['source_receipt_sha256']=source_receipt['receipt_sha256']
    campaign['campaign_sha256']=mechanics._canonical_sha256({
        key:value for key,value in campaign.items() if key!='campaign_sha256'
    })
    campaign_path=tmp_path/'campaign.json'
    plan_path=tmp_path/'plan.json'
    source_receipt_path=tmp_path/'source-receipt.json'
    campaign_path.write_text(json.dumps(campaign),encoding='utf-8')
    plan_path.write_text(json.dumps(plans[target]),encoding='utf-8')
    source_receipt_path.write_text(json.dumps(source_receipt),encoding='utf-8')
    captured={}
    native_trace=[{
        'time_s':0.1,'key_center_z_m':0.01,'tip_center_z_m':0.02,
        'tip_key_separation_m':0.0,'action_index':0,'target_sequence':1,
    }]
    def replay(**kwargs):
        captured.update(kwargs)
        return {
            'status':'PASS','receipt_sha256':'a'*64,'native_trace':native_trace,
            'trajectory_schema':mechanics.STATE_POLICY_TRAJECTORY_SCHEMA,
            'joint_order':['j1','j2','j3','j4','j5','j6'],
            'action_assessments':[],'maximum_joint_tracking_error_rad':0.01,
            'root_pose_invariant':{'all_passed':True},
            'randomized_key_center_board_xy_mm':[1.0,2.0],
        }
    monkeypatch.setattr(mechanics,'run_drive_controlled_robot_h_replay',replay)
    output=tmp_path/'episode-receipt.json'
    trajectory=tmp_path/'trajectory.jsonl'
    status=tmp_path/'status.json'
    result=mechanics.run_randomized_demonstration_episode(
        campaign_path=campaign_path,episode_id=episode['episode_id'],
        replay_plan_path=plan_path,source_receipt_path=source_receipt_path,
        layout_path=tmp_path/'layout.json',drive_profile_path=tmp_path/'drive.json',
        robot_usd_path=tmp_path/'robot.usd',output_path=output,
        trajectory_path=trajectory,status_path=status,
    )
    assert captured['randomized_episode']==episode
    assert result['complete'] is True
    assert result['disposition']=='PASS'
    assert result['failure_reason'] is None
    assert result['trajectory_schema']==mechanics.STATE_POLICY_TRAJECTORY_SCHEMA
    assert result['joint_order']==['j1','j2','j3','j4','j5','j6']
    assert result['trajectory_sha256']==hashlib.sha256(
        trajectory.read_bytes()
    ).hexdigest()
    assert json.loads(output.read_text(encoding='utf-8'))==result


def test_arm218_episode_worker_records_runtime_failure_without_retry(
    arm218_contract,tmp_path,monkeypatch
):
    mechanics,source,plans,source_receipts=arm218_contract
    campaign=mechanics.build_randomized_demonstration_campaign(
        source,plans,source_receipts,master_seed=218
    )
    episode=campaign['episodes'][0]
    target=episode['target_id']
    source_receipt=dict(source_receipts[target])
    source_receipt['source_plan_sha256']=plans[target]['plan_sha256']
    source_receipt['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in source_receipt.items()
        if key!='receipt_sha256'
    })
    episode['source_receipt_sha256']=source_receipt['receipt_sha256']
    campaign['campaign_sha256']=mechanics._canonical_sha256({
        key:value for key,value in campaign.items() if key!='campaign_sha256'
    })
    paths={
        'campaign':tmp_path/'campaign.json','plan':tmp_path/'plan.json',
        'source':tmp_path/'source.json',
    }
    paths['campaign'].write_text(json.dumps(campaign),encoding='utf-8')
    paths['plan'].write_text(json.dumps(plans[target]),encoding='utf-8')
    paths['source'].write_text(json.dumps(source_receipt),encoding='utf-8')
    calls=[]
    def fail(**kwargs):
        calls.append(kwargs)
        raise RuntimeError('simulator unavailable')
    monkeypatch.setattr(mechanics,'run_drive_controlled_robot_h_replay',fail)
    trajectory=tmp_path/'trajectory.jsonl'
    result=mechanics.run_randomized_demonstration_episode(
        campaign_path=paths['campaign'],episode_id=episode['episode_id'],
        replay_plan_path=paths['plan'],source_receipt_path=paths['source'],
        layout_path=tmp_path/'layout.json',drive_profile_path=tmp_path/'drive.json',
        robot_usd_path=tmp_path/'robot.usd',output_path=tmp_path/'receipt.json',
        trajectory_path=trajectory,status_path=tmp_path/'status.json',
    )
    assert len(calls)==1
    assert result['complete'] is True
    assert result['disposition']=='FAIL'
    assert result['failure_reason']=='UNEXPECTED_RUNTIME_ERROR'
    assert trajectory.read_bytes()==b''


def _arm222_compilation_sources():
    mechanics=_load_key_mechanics()
    def signed(value,field):
        value[field]=mechanics._canonical_sha256(value)
        return value
    zero={
        'hardware_access':False,'hardware_writes':0,
        'physical_authority':False,'physical_movements':0,
        'controller_commands':[],'gate_promotions':[],
    }
    episode_id='episode-arm222-contract'
    target_id='1'
    source_receipt_sha='d'*64
    randomized={
        'key_stiffness_n_per_m':100.0,'key_damping_n_s_per_m':0.5,
        'key_mass_kg':0.01,'keyboard_offset_x_mm':1.0,
        'keyboard_offset_y_mm':-1.0,'keyboard_yaw_deg':0.25,
    }
    dataset=signed({
        'schema':mechanics.STATE_POLICY_DATASET_MANIFEST_SCHEMA,
        'status':'READY_FOR_ZERO_AUTHORITY_STATE_POLICY_DATASET',
        'joint_order':['j1','j2','j3','j4','j5','j6'],
        'episodes':[{
            'episode_id':episode_id,'target_id':target_id,
            'role':'EVALUATION','disposition':'PASS','partition':'test',
            'scene_id':'scene-arm222','seed':222,
            'receipt_sha256':source_receipt_sha,'sample_count':2,
            'randomized_parameters':randomized,
            'randomized_key_center_board_xy_mm':[10.0,20.0],
        }],**zero,
    },'dataset_sha256')
    rows=[]
    for index,action_index in enumerate((0,1)):
        rows.append({
            'schema':mechanics.STATE_POLICY_PROPOSAL_ROW_SCHEMA,
            'source_episode_id':episode_id,'source_row_index':index,
            'target_id':target_id,'time_s':0.01*(index+1),
            'phase':'CONTACT','action_index':action_index,
            'target_sequence':index+1,
            'joint_position_proposal_rad':[0.01*(index+joint) for joint in range(6)],
        })
    payload=('\n'.join(
        json.dumps(row,sort_keys=True,separators=(',',':')) for row in rows
    )+'\n').encode()
    proposal=signed({
        'schema':mechanics.STATE_POLICY_PROPOSAL_REPLAY_CAMPAIGN_SCHEMA,
        'status':'READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_QUALIFICATION',
        'source_dataset_sha256':dataset['dataset_sha256'],
        'source_model_sha256':'m'*64,'held_out_episode_count':1,
        'proposal_sample_count':2,'episodes':[{
            'episode_id':episode_id,'target_id':target_id,'partition':'test',
            'scene_id':'scene-arm222','seed':222,
            'source_receipt_sha256':source_receipt_sha,
            'proposal_sample_count':2,
            'proposal_trajectory_sha256':hashlib.sha256(payload).hexdigest(),
        }],**zero,
    },'campaign_sha256')
    request=signed({
        'schema':mechanics.STATE_POLICY_COLLISION_REQUEST_SCHEMA,
        'source_dataset_sha256':dataset['dataset_sha256'],
        'source_model_sha256':proposal['source_model_sha256'],
        'source_proposal_campaign_sha256':proposal['campaign_sha256'],
        'source_proposal_trajectory_sha256':hashlib.sha256(payload).hexdigest(),
        'bounded_sample_count':2,**zero,
    },'request_sha256')
    request_campaign=signed({
        'schema':mechanics.STATE_POLICY_COLLISION_REQUEST_CAMPAIGN_SCHEMA,
        'status':'READY_FOR_ZERO_AUTHORITY_STATE_POLICY_COLLISION_ADMISSION',
        'source_dataset_sha256':dataset['dataset_sha256'],
        'source_model_sha256':proposal['source_model_sha256'],
        'source_proposal_campaign_sha256':proposal['campaign_sha256'],
        'requests':[{
            'episode_id':episode_id,'target_id':target_id,
            'request_sha256':request['request_sha256'],
        }],**zero,
    },'campaign_sha256')
    native=signed({
        'schema':mechanics.STATE_POLICY_NATIVE_COLLISION_MANIFEST_SCHEMA,
        'entries':[{
            'episode_id':episode_id,'target_id':target_id,
            'state_policy_request_sha256':request['request_sha256'],
        }],**zero,
    },'manifest_sha256')
    review=signed({
        'schema':mechanics.STATE_POLICY_NATIVE_COLLISION_REVIEW_SCHEMA,
        'status':'ACCEPTED_FOR_ZERO_AUTHORITY_MECHANICS_PLAN_COMPILATION',
        'next_required_stage':'COMPILE_LM4_ZERO_AUTHORITY_MECHANICS_REPLAY_PLANS',
        'source_dataset_sha256':dataset['dataset_sha256'],
        'source_model_sha256':proposal['source_model_sha256'],
        'source_manifest_sha256':native['manifest_sha256'],
        'episode_count':1,'total_bounded_sample_count':2,
        'review_decision':{
            'mechanics_plan_compilation_allowed':True,
            'mechanics_replay_execution_authorized':False,
        },
        'reviewed_episodes':[{
            'episode_id':episode_id,'target_id':target_id,
            'receipt_sha256':'n'*64,
        }],**zero,
    },'review_sha256')
    mechanics_profile=signed({
        'schema':mechanics.PROFILE_SCHEMA,
        'regions':[],**zero,
    },'profile_sha256')
    virtual_profile_bytes=json.dumps({
        'schema':'rocell.virtual_commissioning_profile.v1',
        'status':'UNMEASURED_SENSITIVITY_OVERLAY',
        'simulation_only':True,'physical_release_effect':'NONE',
    },sort_keys=True).encode()
    drive_profile_bytes=json.dumps({
        'schema':mechanics.GEOMETRY_PRIOR_PROFILE_SCHEMA,
        'status':'PROVISIONAL_SIMULATION_ONLY',
        'simulation_only':True,'physical_authority':False,
        'physics_dt_s':1.0/120.0,
    },sort_keys=True).encode()
    robot_usd_bytes=b'#usda 1.0\n'
    import_receipt=signed({
        'schema':'tactevra.isaac_sim_urdf_import.v1',
        'external_files':[{
            'sha256':hashlib.sha256(robot_usd_bytes).hexdigest(),
            'size_bytes':len(robot_usd_bytes),
        }],**zero,
    },'receipt_sha256')
    bindings={
        'key_mechanics_profile_sha256':mechanics_profile['profile_sha256'],
        'virtual_profile_sha256':hashlib.sha256(
            virtual_profile_bytes
        ).hexdigest(),
        'drive_profile_file_sha256':hashlib.sha256(
            drive_profile_bytes
        ).hexdigest(),
        'robot_import_receipt_sha256':import_receipt['receipt_sha256'],
        'robot_usd_sha256':hashlib.sha256(robot_usd_bytes).hexdigest(),
    }
    plans=[]
    receipts={}
    results=[]
    for target in mechanics.REPRESENTATIVE_KEYS[1:]:
        plan=signed({
            'schema':(
                mechanics.REPRESENTATIVE_KEY_CONTACT_REFINED_MECHANICS_REPLAY_PLAN_SCHEMA
            ),
            'status':'READY_FOR_ZERO_AUTHORITY_CONTACT_REFINED_KEY_MECHANICS_REPLAY',
            'target_id':target,'joint_order':dataset['joint_order'],
            'target_region':{'center_board_xy_mm':[10.0,20.0]},
            'robot_placement_matrix_row_major':[1.0]*16,
            'execution_contract':{'maximum_joint_tracking_error_rad':0.05},
            'source_bindings':bindings,**zero,
        },'plan_sha256')
        receipt=signed({
            'schema':mechanics.REPRESENTATIVE_KEY_NATIVE_MECHANICS_RECEIPT_SCHEMA,
            'status':'PASS','target_id':target,
            'source_plan_sha256':plan['plan_sha256'],**zero,
        },'receipt_sha256')
        plans.append(plan)
        receipts[target]=receipt
        results.append({
            'target_id':target,'plan_sha256':plan['plan_sha256'],
            'receipt_sha256':receipt['receipt_sha256'],'action_count':2,
            'root_pose_invariant_passed':True,
        })
    source_campaign=signed({
        'schema':mechanics.REPRESENTATIVE_KEY_CONTACT_REFINED_MECHANICS_CAMPAIGN_SCHEMA,
        'status':'READY_FOR_ZERO_AUTHORITY_CONTACT_REFINED_MECHANICS_REPLAY',
        'plans':plans,**zero,
    },'campaign_sha256')
    source_result=signed({
        'schema':mechanics.REPRESENTATIVE_KEY_NATIVE_MECHANICS_RESULT_CAMPAIGN_SCHEMA,
        'status':'PASS_REPRESENTATIVE_ZERO_AUTHORITY_NATIVE_MECHANICS_CAMPAIGN',
        'source_replay_campaign_sha256':source_campaign['campaign_sha256'],
        'accepted_action_count':8,'results':results,**zero,
    },'campaign_sha256')
    sources=(
        review,dataset,proposal,{episode_id:payload},request_campaign,
        {episode_id:request},native,source_campaign,source_result,receipts,
    )
    runtime=(
        mechanics_profile,virtual_profile_bytes,drive_profile_bytes,
        import_receipt,robot_usd_bytes,
    )
    return mechanics,sources,runtime


def test_arm222_mechanics_plan_compilation_is_deterministic_and_nonexecuting():
    mechanics,sources,_runtime=_arm222_compilation_sources()
    first,first_plans=mechanics.compile_state_policy_mechanics_replay_campaign(
        *sources
    )
    second,second_plans=mechanics.compile_state_policy_mechanics_replay_campaign(
        *sources
    )
    assert first==second and first_plans==second_plans
    assert first['schema']==mechanics.STATE_POLICY_MECHANICS_REPLAY_CAMPAIGN_SCHEMA
    assert first['episode_count']==1
    assert first['total_joint_target_count']==2
    assert first['total_collision_screened_bounded_sample_count']==2
    plan=next(iter(first_plans.values()))
    assert plan['contact_endpoint_sequences']==[0,1]
    assert [row['phase_endpoint'] for row in plan['joint_targets']]==[True,True]
    assert plan['proposal_semantics'][
        'proposal_targets_preserved_without_interpolation'
    ] is True
    assert plan['native_mechanics_replay_executed'] is False
    assert plan['hardware_access'] is plan['physical_authority'] is False
    assert first['isaac_started'] is first['gpu_started'] is False


def test_arm222_mechanics_plan_compilation_rejects_tampering_and_denominator_drift():
    mechanics,sources,_runtime=_arm222_compilation_sources()
    tampered=list(sources)
    payloads=dict(tampered[3])
    episode_id=next(iter(payloads))
    payloads[episode_id]+=b'{}\n'
    tampered[3]=payloads
    with pytest.raises(mechanics.MechanicsContractError,match='proposal digest'):
        mechanics.compile_state_policy_mechanics_replay_campaign(*tampered)
    tampered=list(sources)
    proposal=json.loads(json.dumps(tampered[2]))
    proposal['proposal_sample_count']=3
    proposal['campaign_sha256']=mechanics._canonical_sha256({
        key:value for key,value in proposal.items() if key!='campaign_sha256'
    })
    tampered[2]=proposal
    with pytest.raises(mechanics.MechanicsContractError,match='boundary|lineage|denominator'):
        mechanics.compile_state_policy_mechanics_replay_campaign(*tampered)


def test_arm223_runtime_admission_is_deterministic_and_nonexecuting():
    mechanics,sources,runtime=_arm222_compilation_sources()
    campaign,plans=mechanics.compile_state_policy_mechanics_replay_campaign(*sources)
    first,first_receipts=mechanics.admit_state_policy_mechanics_runtime_inputs(
        campaign,plans,*runtime
    )
    second,second_receipts=mechanics.admit_state_policy_mechanics_runtime_inputs(
        campaign,plans,*runtime
    )
    assert first==second and first_receipts==second_receipts
    assert first['schema']==(
        mechanics.STATE_POLICY_MECHANICS_RUNTIME_ADMISSION_CAMPAIGN_SCHEMA
    )
    assert first['admission_count']==1
    assert first['total_joint_target_count']==2
    assert first['total_collision_screened_bounded_sample_count']==2
    assert first['revalidated_file_count']==5
    assert first['runtime_files_revalidated'] is True
    assert first['isaac_started'] is first['gpu_started'] is False
    assert first['mechanics_replays_executed']==0
    assert first['hardware_access'] is first['physical_authority'] is False
    receipt=next(iter(first_receipts.values()))
    assert receipt['joint_target_count']==2
    assert receipt['contact_endpoint_sequences']==[0,1]
    assert receipt['mechanics_replay_executed'] is False


def test_arm223_runtime_admission_rejects_runtime_and_plan_tampering():
    mechanics,sources,runtime=_arm222_compilation_sources()
    campaign,plans=mechanics.compile_state_policy_mechanics_replay_campaign(*sources)
    changed_runtime=list(runtime)
    changed_runtime[2]+=b'\n'
    with pytest.raises(mechanics.MechanicsContractError,match='lineage changed'):
        mechanics.admit_state_policy_mechanics_runtime_inputs(
            campaign,plans,*changed_runtime
        )
    changed_plans=json.loads(json.dumps(plans))
    episode_id=next(iter(changed_plans))
    changed_plans[episode_id]['joint_targets'][0][
        'joint_position_target_rad'
    ][0]+=0.1
    with pytest.raises(mechanics.MechanicsContractError,match='sha256 mismatch'):
        mechanics.admit_state_policy_mechanics_runtime_inputs(
            campaign,changed_plans,*runtime
        )


def test_arm224_native_mechanics_materialization_is_deterministic_and_nonexecuting():
    mechanics,sources,runtime=_arm222_compilation_sources()
    mechanics_campaign,plans=(
        mechanics.compile_state_policy_mechanics_replay_campaign(*sources)
    )
    admission_campaign,admissions=(
        mechanics.admit_state_policy_mechanics_runtime_inputs(
            mechanics_campaign,plans,*runtime
        )
    )
    first,first_plans=mechanics.materialize_state_policy_native_mechanics_inputs(
        admission_campaign,admissions,mechanics_campaign,plans
    )
    second,second_plans=mechanics.materialize_state_policy_native_mechanics_inputs(
        admission_campaign,admissions,mechanics_campaign,plans
    )
    assert first==second and first_plans==second_plans
    assert first['schema']==mechanics.STATE_POLICY_NATIVE_MECHANICS_MANIFEST_SCHEMA
    assert first['episode_count']==1
    assert first['total_joint_target_count']==2
    assert first['total_collision_screened_bounded_sample_count']==2
    assert first['runtime_files_revalidated'] is True
    assert first['isaac_started'] is first['gpu_started'] is False
    assert first['mechanics_replays_executed']==0
    assert first['prior_mechanics_results_reused'] is False
    assert first['hardware_access'] is first['physical_authority'] is False
    native_plan=next(iter(first_plans.values()))
    source_plan=next(iter(plans.values()))
    admission=next(iter(admissions.values()))
    assert native_plan['schema']==(
        mechanics.STATE_POLICY_NATIVE_MECHANICS_REPLAY_PLAN_SCHEMA
    )
    assert native_plan['joint_targets']==source_plan['joint_targets']
    assert native_plan['randomized_parameters']==source_plan['randomized_parameters']
    assert native_plan['contact_endpoint_sequences']==[0,1]
    assert native_plan['source_mechanics_plan_sha256']==source_plan['plan_sha256']
    assert native_plan['source_runtime_admission_receipt_sha256']==(
        admission['receipt_sha256']
    )
    assert native_plan['runtime_admission_required'] is False
    assert native_plan['prior_mechanics_result_reused'] is False
    assert native_plan['native_mechanics_replay_executed'] is False


def test_arm224_native_mechanics_materialization_rejects_lineage_and_denominator_drift():
    mechanics,sources,runtime=_arm222_compilation_sources()
    mechanics_campaign,plans=(
        mechanics.compile_state_policy_mechanics_replay_campaign(*sources)
    )
    admission_campaign,admissions=(
        mechanics.admit_state_policy_mechanics_runtime_inputs(
            mechanics_campaign,plans,*runtime
        )
    )
    changed_admissions=json.loads(json.dumps(admissions))
    episode_id=next(iter(changed_admissions))
    changed_admissions[episode_id]['joint_target_count']=3
    with pytest.raises(mechanics.MechanicsContractError,match='sha256 mismatch'):
        mechanics.materialize_state_policy_native_mechanics_inputs(
            admission_campaign,changed_admissions,mechanics_campaign,plans
        )
    with pytest.raises(mechanics.MechanicsContractError,match='denominator changed'):
        mechanics.materialize_state_policy_native_mechanics_inputs(
            admission_campaign,admissions,mechanics_campaign,{}
        )


def test_arm225_native_mechanics_episode_admission_accepts_exact_arm224_plan():
    mechanics,sources,runtime=_arm222_compilation_sources()
    mechanics_campaign,plans=(
        mechanics.compile_state_policy_mechanics_replay_campaign(*sources)
    )
    admission_campaign,admissions=(
        mechanics.admit_state_policy_mechanics_runtime_inputs(
            mechanics_campaign,plans,*runtime
        )
    )
    manifest,native_plans=(
        mechanics.materialize_state_policy_native_mechanics_inputs(
            admission_campaign,admissions,mechanics_campaign,plans
        )
    )
    episode_id=next(iter(native_plans))
    entry=mechanics.validate_state_policy_native_mechanics_episode(
        manifest,native_plans[episode_id],episode_id
    )
    assert entry['episode_id']==episode_id
    assert entry['joint_target_count']==2
    assert entry['contact_endpoint_sequences']==[0,1]
    assert manifest['isaac_started'] is manifest['gpu_started'] is False


def test_arm225_native_mechanics_episode_admission_rejects_wrong_plan_and_manifest():
    mechanics,sources,runtime=_arm222_compilation_sources()
    mechanics_campaign,plans=(
        mechanics.compile_state_policy_mechanics_replay_campaign(*sources)
    )
    admission_campaign,admissions=(
        mechanics.admit_state_policy_mechanics_runtime_inputs(
            mechanics_campaign,plans,*runtime
        )
    )
    manifest,native_plans=(
        mechanics.materialize_state_policy_native_mechanics_inputs(
            admission_campaign,admissions,mechanics_campaign,plans
        )
    )
    episode_id=next(iter(native_plans))
    changed_plan=json.loads(json.dumps(native_plans[episode_id]))
    changed_plan['sample_count']=3
    with pytest.raises(mechanics.MechanicsContractError,match='sha256 mismatch'):
        mechanics.validate_state_policy_native_mechanics_episode(
            manifest,changed_plan,episode_id
        )
    with pytest.raises(
        mechanics.MechanicsContractError,match='absent or duplicated'
    ):
        mechanics.validate_state_policy_native_mechanics_episode(
            manifest,native_plans[episode_id],'episode-not-declared'
        )


def test_arm225_runtime_failure_receipt_retains_lineage_without_claiming_trace():
    mechanics,sources,runtime=_arm222_compilation_sources()
    mechanics_campaign,plans=(
        mechanics.compile_state_policy_mechanics_replay_campaign(*sources)
    )
    admission_campaign,admissions=(
        mechanics.admit_state_policy_mechanics_runtime_inputs(
            mechanics_campaign,plans,*runtime
        )
    )
    manifest,native_plans=(
        mechanics.materialize_state_policy_native_mechanics_inputs(
            admission_campaign,admissions,mechanics_campaign,plans
        )
    )
    episode_id=next(iter(native_plans))
    plan=native_plans[episode_id]
    receipt=mechanics.build_state_policy_native_mechanics_failure_receipt(
        manifest_sha256=manifest['manifest_sha256'],
        plan=plan,
        error_type='RuntimeError',
        error_message='root invariant failed at sequence 1',
    )
    assert receipt['status']=='BLOCKED_STATE_POLICY_NATIVE_MECHANICS_REPLAY'
    assert receipt['failure_reason']=='ROOT_INVARIANT'
    assert receipt['stopped_at_sequence']==1
    assert receipt['stopped_phase']=='CONTACT'
    assert receipt['source_plan_sha256']==plan['plan_sha256']
    assert receipt['native_trace_retained'] is False
    assert receipt['automatic_retry_performed'] is False
    assert receipt['hardware_access'] is receipt['physical_authority'] is False
    mechanics._verify_lm3_digest(
        receipt,'receipt_sha256','state-policy failure receipt'
    )


def test_arm227_root_drift_plan_is_exact_bounded_and_nonexecuting():
    mechanics,sources,runtime=_arm222_compilation_sources()
    mechanics_campaign,plans=(
        mechanics.compile_state_policy_mechanics_replay_campaign(*sources)
    )
    admission_campaign,admissions=(
        mechanics.admit_state_policy_mechanics_runtime_inputs(
            mechanics_campaign,plans,*runtime
        )
    )
    manifest,native_plans=mechanics.materialize_state_policy_native_mechanics_inputs(
        admission_campaign,admissions,mechanics_campaign,plans
    )
    native_plan=next(iter(native_plans.values()))
    failure=mechanics.build_state_policy_native_mechanics_failure_receipt(
        manifest_sha256=manifest['manifest_sha256'],
        plan=native_plan,
        error_type='RuntimeError',
        error_message='root invariant failed at sequence 0',
    )
    first=mechanics.build_state_policy_root_drift_diagnostic_plan(
        manifest,native_plan,failure
    )
    second=mechanics.build_state_policy_root_drift_diagnostic_plan(
        manifest,native_plan,failure
    )
    assert first==second
    assert first['schema']==(
        mechanics.STATE_POLICY_ROOT_DRIFT_DIAGNOSTIC_PLAN_SCHEMA
    )
    assert first['source_manifest_sha256']==manifest['manifest_sha256']
    assert first['source_plan_sha256']==native_plan['plan_sha256']
    assert first['source_failure_receipt_sha256']==failure['receipt_sha256']
    assert first['observed_failure']['failure_preceded_contact'] is True
    comparison=first['fixture_comparison']
    assert comparison['failed_state_policy_path']=={
        'solver_position_iteration_count':64,
        'solver_velocity_iteration_count_authored':False,
        'fixed_joint_enabled_explicitly':False,
    }
    assert comparison['known_passing_fixed_base_path']=={
        'solver_position_iteration_count':64,
        'solver_velocity_iteration_count':8,
        'fixed_joint_enabled_explicitly':True,
    }
    probe=first['probe_contract']
    assert probe['trajectory_playback'] is probe['key_contact'] is False
    assert probe['joint_target_commands']==0
    assert len(probe['checkpoints'])==4
    assert first['isaac_started'] is first['gpu_started'] is False
    assert first['diagnostics_executed']==0
    assert first['hardware_access'] is first['physical_authority'] is False
    mechanics._require_canonical_hash(first,'plan_sha256','root drift plan')


def test_arm227_root_drift_plan_rejects_failure_lineage_drift():
    mechanics,sources,runtime=_arm222_compilation_sources()
    mechanics_campaign,plans=(
        mechanics.compile_state_policy_mechanics_replay_campaign(*sources)
    )
    admission_campaign,admissions=(
        mechanics.admit_state_policy_mechanics_runtime_inputs(
            mechanics_campaign,plans,*runtime
        )
    )
    manifest,native_plans=mechanics.materialize_state_policy_native_mechanics_inputs(
        admission_campaign,admissions,mechanics_campaign,plans
    )
    native_plan=next(iter(native_plans.values()))
    failure=mechanics.build_state_policy_native_mechanics_failure_receipt(
        manifest_sha256=manifest['manifest_sha256'],
        plan=native_plan,
        error_type='RuntimeError',
        error_message='root invariant failed at sequence 0',
    )
    changed=json.loads(json.dumps(failure))
    changed['source_plan_sha256']='0'*64
    changed.pop('receipt_sha256')
    changed['receipt_sha256']=mechanics._canonical_sha256(changed)
    with pytest.raises(mechanics.MechanicsContractError,match='lineage changed'):
        mechanics.build_state_policy_root_drift_diagnostic_plan(
            manifest,native_plan,changed
        )


def test_arm228_root_drift_runtime_admission_reopens_exact_inputs():
    mechanics,sources,runtime=_arm222_compilation_sources()
    mechanics_campaign,plans=(
        mechanics.compile_state_policy_mechanics_replay_campaign(*sources)
    )
    admission_campaign,admissions=(
        mechanics.admit_state_policy_mechanics_runtime_inputs(
            mechanics_campaign,plans,*runtime
        )
    )
    manifest,native_plans=mechanics.materialize_state_policy_native_mechanics_inputs(
        admission_campaign,admissions,mechanics_campaign,plans
    )
    native_plan=next(iter(native_plans.values()))
    failure=mechanics.build_state_policy_native_mechanics_failure_receipt(
        manifest_sha256=manifest['manifest_sha256'],
        plan=native_plan,
        error_type='RuntimeError',
        error_message='root invariant failed at sequence 0',
    )
    diagnostic=mechanics.build_state_policy_root_drift_diagnostic_plan(
        manifest,native_plan,failure
    )
    drive_profile=mechanics.validate_state_policy_root_drift_diagnostic_inputs(
        diagnostic,manifest,native_plan,failure,runtime[2],runtime[4]
    )
    assert drive_profile['schema']==mechanics.GEOMETRY_PRIOR_PROFILE_SCHEMA
    assert drive_profile['simulation_only'] is True
    assert drive_profile['physical_authority'] is False


def test_arm228_root_drift_runtime_admission_rejects_plan_and_file_drift():
    mechanics,sources,runtime=_arm222_compilation_sources()
    mechanics_campaign,plans=(
        mechanics.compile_state_policy_mechanics_replay_campaign(*sources)
    )
    admission_campaign,admissions=(
        mechanics.admit_state_policy_mechanics_runtime_inputs(
            mechanics_campaign,plans,*runtime
        )
    )
    manifest,native_plans=mechanics.materialize_state_policy_native_mechanics_inputs(
        admission_campaign,admissions,mechanics_campaign,plans
    )
    native_plan=next(iter(native_plans.values()))
    failure=mechanics.build_state_policy_native_mechanics_failure_receipt(
        manifest_sha256=manifest['manifest_sha256'],
        plan=native_plan,
        error_type='RuntimeError',
        error_message='root invariant failed at sequence 0',
    )
    diagnostic=mechanics.build_state_policy_root_drift_diagnostic_plan(
        manifest,native_plan,failure
    )
    changed=json.loads(json.dumps(diagnostic))
    changed['probe_contract']['joint_target_commands']=1
    changed.pop('plan_sha256')
    changed['plan_sha256']=mechanics._canonical_sha256(changed)
    with pytest.raises(mechanics.MechanicsContractError,match='plan changed'):
        mechanics.validate_state_policy_root_drift_diagnostic_inputs(
            changed,manifest,native_plan,failure,runtime[2],runtime[4]
        )
    with pytest.raises(mechanics.MechanicsContractError,match='file lineage'):
        mechanics.validate_state_policy_root_drift_diagnostic_inputs(
            diagnostic,manifest,native_plan,failure,runtime[2]+b'\n',runtime[4]
        )


def test_arm229_root_drift_receipt_is_persisted_before_fast_app_close():
    mechanics=_load_key_mechanics()
    source=inspect.getsource(mechanics.run_state_policy_root_drift_diagnostic)
    output_write=source.index('output_path.write_text(')
    status_write=source.index('status_path.write_text(')
    app_close=source.index('app.close()')
    assert output_write < status_write < app_close
    assert source.index('finally:', status_write) < app_close


def test_arm230_reviews_exact_static_fixture_denominator_and_rejects_drift():
    mechanics,sources,runtime=_arm222_compilation_sources()
    mechanics_campaign,plans=(
        mechanics.compile_state_policy_mechanics_replay_campaign(*sources)
    )
    admission_campaign,admissions=(
        mechanics.admit_state_policy_mechanics_runtime_inputs(
            mechanics_campaign,plans,*runtime
        )
    )
    manifest,native_plans=mechanics.materialize_state_policy_native_mechanics_inputs(
        admission_campaign,admissions,mechanics_campaign,plans
    )
    native_plan=next(iter(native_plans.values()))
    failure=mechanics.build_state_policy_native_mechanics_failure_receipt(
        manifest_sha256=manifest['manifest_sha256'],
        plan=native_plan,
        error_type='RuntimeError',
        error_message='root invariant failed at sequence 0',
    )
    diagnostic=mechanics.build_state_policy_root_drift_diagnostic_plan(
        manifest,native_plan,failure
    )
    records=[]
    for index,checkpoint in enumerate(diagnostic['probe_contract']['checkpoints']):
        records.append({
            'checkpoint':checkpoint,
            'observed_position_m':[0.385,0.532,0.0701],
            'observed_quaternion_wxyz':[1.0,0.0,0.0,0.0],
            'translation_delta_mm':index*0.001,
            'orientation_delta_deg':0.0,
            'translation_tolerance_mm':0.05,
            'orientation_tolerance_deg':0.1,
            'passed':True,
        })
    receipt={
        'schema':mechanics.STATE_POLICY_ROOT_DRIFT_DIAGNOSTIC_RECEIPT_SCHEMA,
        'status':'PASS_ZERO_AUTHORITY_ROOT_FIXTURE_DIAGNOSTIC',
        'complete':True,
        'root_invariant_all_passed':True,
        'checkpoint_records':records,
        'checkpoint_count':4,
        'source_diagnostic_plan_sha256':diagnostic['plan_sha256'],
        'source_manifest_sha256':manifest['manifest_sha256'],
        'source_plan_sha256':native_plan['plan_sha256'],
        'source_failure_receipt_sha256':failure['receipt_sha256'],
        'fixture_configuration':diagnostic['fixture_comparison'][
            'known_passing_fixed_base_path'
        ],
        'translation_tolerance_mm':0.05,
        'orientation_tolerance_deg':0.1,
        'maximum_translation_delta_mm':0.003,
        'maximum_orientation_delta_deg':0.0,
        'trajectory_playback':False,
        'joint_target_commands':0,
        'key_contact':False,
        'automatic_retry_performed':False,
        'isaac_started':True,
        'gpu_started':True,
        'diagnostics_executed':1,
        'hardware_access':False,
        'hardware_writes':0,
        'physical_authority':False,
        'physical_movements':0,
        'controller_commands':[],
        'gate_promotions':[],
        'next_required_stage':'REVIEW_ROOT_FIXTURE_DIAGNOSTIC',
    }
    receipt['receipt_sha256']=mechanics._canonical_sha256(receipt)
    first=mechanics.review_state_policy_root_fixture_diagnostic(
        receipt,diagnostic,manifest,native_plan,failure
    )
    second=mechanics.review_state_policy_root_fixture_diagnostic(
        receipt,diagnostic,manifest,native_plan,failure
    )
    assert first==second
    assert first['status']==(
        'ACCEPTED_FOR_ZERO_AUTHORITY_STATE_POLICY_FIXTURE_CORRECTION'
    )
    assert first['checkpoint_count']==4
    assert first['maximum_translation_delta_mm']==0.003
    assert first['review_decision']['mechanics_replay_authorized'] is False
    changed=json.loads(json.dumps(receipt))
    changed['checkpoint_records'][2]['passed']=False
    changed.pop('receipt_sha256')
    changed['receipt_sha256']=mechanics._canonical_sha256(changed)
    with pytest.raises(mechanics.MechanicsContractError,match='checkpoint changed'):
        mechanics.review_state_policy_root_fixture_diagnostic(
            changed,diagnostic,manifest,native_plan,failure
        )


def _arm231_fixture_review_sources():
    mechanics,sources,runtime=_arm222_compilation_sources()
    mechanics_campaign,plans=(
        mechanics.compile_state_policy_mechanics_replay_campaign(*sources)
    )
    admission_campaign,admissions=(
        mechanics.admit_state_policy_mechanics_runtime_inputs(
            mechanics_campaign,plans,*runtime
        )
    )
    manifest,native_plans=mechanics.materialize_state_policy_native_mechanics_inputs(
        admission_campaign,admissions,mechanics_campaign,plans
    )
    native_plan=next(iter(native_plans.values()))
    failure=mechanics.build_state_policy_native_mechanics_failure_receipt(
        manifest_sha256=manifest['manifest_sha256'],
        plan=native_plan,
        error_type='RuntimeError',
        error_message='root invariant failed at sequence 0',
    )
    diagnostic=mechanics.build_state_policy_root_drift_diagnostic_plan(
        manifest,native_plan,failure
    )
    records=[{
        'checkpoint':checkpoint,
        'observed_position_m':[0.385,0.532,0.0701],
        'observed_quaternion_wxyz':[1.0,0.0,0.0,0.0],
        'translation_delta_mm':index*0.001,
        'orientation_delta_deg':0.0,
        'translation_tolerance_mm':0.05,
        'orientation_tolerance_deg':0.1,
        'passed':True,
    } for index,checkpoint in enumerate(diagnostic['probe_contract']['checkpoints'])]
    receipt={
        'schema':mechanics.STATE_POLICY_ROOT_DRIFT_DIAGNOSTIC_RECEIPT_SCHEMA,
        'status':'PASS_ZERO_AUTHORITY_ROOT_FIXTURE_DIAGNOSTIC',
        'complete':True,
        'root_invariant_all_passed':True,
        'checkpoint_records':records,
        'checkpoint_count':4,
        'source_diagnostic_plan_sha256':diagnostic['plan_sha256'],
        'source_manifest_sha256':manifest['manifest_sha256'],
        'source_plan_sha256':native_plan['plan_sha256'],
        'source_failure_receipt_sha256':failure['receipt_sha256'],
        'fixture_configuration':diagnostic['fixture_comparison'][
            'known_passing_fixed_base_path'
        ],
        'translation_tolerance_mm':0.05,
        'orientation_tolerance_deg':0.1,
        'maximum_translation_delta_mm':0.003,
        'maximum_orientation_delta_deg':0.0,
        'trajectory_playback':False,
        'joint_target_commands':0,
        'key_contact':False,
        'automatic_retry_performed':False,
        'isaac_started':True,
        'gpu_started':True,
        'diagnostics_executed':1,
        'hardware_access':False,
        'hardware_writes':0,
        'physical_authority':False,
        'physical_movements':0,
        'controller_commands':[],
        'gate_promotions':[],
        'next_required_stage':'REVIEW_ROOT_FIXTURE_DIAGNOSTIC',
    }
    receipt['receipt_sha256']=mechanics._canonical_sha256(receipt)
    review=mechanics.review_state_policy_root_fixture_diagnostic(
        receipt,diagnostic,manifest,native_plan,failure
    )
    return mechanics,review,manifest,native_plans


def test_arm231_applies_review_bound_fixture_correction_deterministically_offline():
    mechanics,review,manifest,native_plans=_arm231_fixture_review_sources()
    first,first_plans=mechanics.apply_state_policy_fixed_fixture_correction(
        review,manifest,native_plans
    )
    second,second_plans=mechanics.apply_state_policy_fixed_fixture_correction(
        review,manifest,native_plans
    )
    assert first==second and first_plans==second_plans
    assert first['schema']==(
        mechanics.STATE_POLICY_FIXED_FIXTURE_NATIVE_MECHANICS_MANIFEST_SCHEMA
    )
    assert first['source_uncorrected_manifest_sha256']==manifest['manifest_sha256']
    assert first['source_root_fixture_review_sha256']==review['review_sha256']
    assert first['fixed_fixture_configuration']=={
        'solver_position_iteration_count':64,
        'solver_velocity_iteration_count':8,
        'fixed_joint_enabled_explicitly':True,
    }
    assert first['isaac_started'] is first['gpu_started'] is False
    assert first['mechanics_replays_executed']==0
    assert first['native_replay_authorized'] is False
    corrected=next(iter(first_plans.values()))
    source=next(iter(native_plans.values()))
    assert corrected['schema']==(
        mechanics.STATE_POLICY_FIXED_FIXTURE_NATIVE_MECHANICS_REPLAY_PLAN_SCHEMA
    )
    assert corrected['source_uncorrected_plan_sha256']==source['plan_sha256']
    assert corrected['fixed_fixture_correction_applied'] is True
    assert corrected['native_replay_authorized'] is False
    assert corrected['joint_targets']==source['joint_targets']
    assert corrected['plan_sha256']!=source['plan_sha256']


def test_arm231_rejects_review_or_source_denominator_drift():
    mechanics,review,manifest,native_plans=_arm231_fixture_review_sources()
    changed=json.loads(json.dumps(review))
    changed['review_decision']['offline_fixture_correction_allowed']=False
    changed.pop('review_sha256')
    changed['review_sha256']=mechanics._canonical_sha256(changed)
    with pytest.raises(mechanics.MechanicsContractError,match='boundary changed'):
        mechanics.apply_state_policy_fixed_fixture_correction(
            changed,manifest,native_plans
        )
    with pytest.raises(mechanics.MechanicsContractError,match='denominator changed'):
        mechanics.apply_state_policy_fixed_fixture_correction(review,manifest,{})


def test_arm231_independent_review_reproduces_every_corrected_hash():
    mechanics,fixture_review,manifest,native_plans=(
        _arm231_fixture_review_sources()
    )
    corrected_manifest,corrected_plans=(
        mechanics.apply_state_policy_fixed_fixture_correction(
            fixture_review,manifest,native_plans
        )
    )
    first=mechanics.review_state_policy_fixed_fixture_correction(
        fixture_review,manifest,native_plans,corrected_manifest,corrected_plans
    )
    second=mechanics.review_state_policy_fixed_fixture_correction(
        fixture_review,manifest,native_plans,corrected_manifest,corrected_plans
    )
    assert first==second
    assert first['schema']==(
        mechanics.STATE_POLICY_FIXED_FIXTURE_CORRECTION_REVIEW_SCHEMA
    )
    assert first['reviewed_episode_count']==1
    assert first['review_decision']['trajectory_samples_unchanged'] is True
    assert first['review_decision']['all_corrected_hashes_reproduced'] is True
    assert first['review_decision']['native_replay_authorized'] is False
    assert first['isaac_started'] is first['gpu_started'] is False
    changed=json.loads(json.dumps(corrected_plans))
    episode_id=next(iter(changed))
    changed[episode_id]['fixed_fixture_configuration'][
        'solver_velocity_iteration_count'
    ]=7
    changed[episode_id].pop('plan_sha256')
    changed[episode_id]['plan_sha256']=mechanics._canonical_sha256(
        changed[episode_id]
    )
    with pytest.raises(mechanics.MechanicsContractError,match='inputs changed'):
        mechanics.review_state_policy_fixed_fixture_correction(
            fixture_review,manifest,native_plans,corrected_manifest,changed
        )


def test_arm231_runtime_authors_the_proven_fixed_fixture_configuration():
    mechanics=_load_key_mechanics()
    source=inspect.getsource(mechanics.run_drive_controlled_robot_h_replay)
    assert 'CreateSolverPositionIterationCountAttr' in source
    assert 'CreateSolverVelocityIterationCountAttr' in source
    assert 'fixed.CreateJointEnabledAttr().Set(True)' in source


def _arm232_single_replay_request_sources():
    mechanics,fixture_review,manifest,native_plans=(
        _arm231_fixture_review_sources()
    )
    corrected_manifest,corrected_plans=(
        mechanics.apply_state_policy_fixed_fixture_correction(
            fixture_review,manifest,native_plans
        )
    )
    correction_review=mechanics.review_state_policy_fixed_fixture_correction(
        fixture_review,
        manifest,
        native_plans,
        corrected_manifest,
        corrected_plans,
    )
    episode_id=next(iter(corrected_plans))
    return (
        mechanics,
        correction_review,
        corrected_manifest,
        corrected_plans[episode_id],
        episode_id,
    )


def test_arm232_builds_one_attempt_corrected_replay_request_offline():
    mechanics,review,manifest,plan,episode_id=(
        _arm232_single_replay_request_sources()
    )
    first=mechanics.build_state_policy_fixed_fixture_single_replay_request(
        review,manifest,plan,episode_id
    )
    second=mechanics.build_state_policy_fixed_fixture_single_replay_request(
        review,manifest,plan,episode_id
    )
    assert first==second
    assert first['schema']==(
        mechanics.STATE_POLICY_FIXED_FIXTURE_SINGLE_REPLAY_REQUEST_SCHEMA
    )
    assert first['status']==(
        'READY_FOR_EXPLICIT_ONE_ATTEMPT_ZERO_AUTHORITY_AUTHORIZATION'
    )
    assert first['episode_id']==episode_id
    assert first['target_id']==plan['target_id']
    assert first['joint_target_count']==plan['sample_count']
    assert first['source_corrected_plan_sha256']==plan['plan_sha256']
    assert first['attempt_contract']['maximum_attempt_count']==1
    assert first['attempt_contract']['automatic_retry_allowed'] is False
    assert first['attempt_contract']['fresh_runtime_file_revalidation_required'] is True
    assert first['native_replay_authorized'] is False
    assert first['isaac_started'] is first['gpu_started'] is False
    assert first['mechanics_replays_executed']==0
    assert first['hardware_access'] is first['physical_authority'] is False
    assert first['next_required_stage']==(
        'OBTAIN_EXPLICIT_ONE_ATTEMPT_ZERO_AUTHORITY_NATIVE_REPLAY_AUTHORIZATION'
    )


def test_arm232_rejects_review_plan_or_episode_drift():
    mechanics,review,manifest,plan,episode_id=(
        _arm232_single_replay_request_sources()
    )
    changed_review=json.loads(json.dumps(review))
    changed_review['review_decision']['native_replay_authorized']=True
    changed_review.pop('review_sha256')
    changed_review['review_sha256']=mechanics._canonical_sha256(changed_review)
    with pytest.raises(mechanics.MechanicsContractError,match='review boundary'):
        mechanics.build_state_policy_fixed_fixture_single_replay_request(
            changed_review,manifest,plan,episode_id
        )

    changed_plan=json.loads(json.dumps(plan))
    changed_plan['target_id']='ENTER'
    changed_plan.pop('plan_sha256')
    changed_plan['plan_sha256']=mechanics._canonical_sha256(changed_plan)
    with pytest.raises(mechanics.MechanicsContractError,match='lineage changed'):
        mechanics.build_state_policy_fixed_fixture_single_replay_request(
            review,manifest,changed_plan,episode_id
        )

    with pytest.raises(mechanics.MechanicsContractError,match='absent or duplicated'):
        mechanics.build_state_policy_fixed_fixture_single_replay_request(
            review,manifest,plan,'episode-not-reviewed'
        )


def test_arm233_admits_exact_authorization_once_after_fresh_hashes(
    tmp_path, monkeypatch
):
    mechanics=_load_key_mechanics()
    episode_id='episode-test'
    authorization=(
        'I authorize exactly one ARM-232 zero-authority native mechanics '
        'replay for episode-test (SPACE), with no automatic retry and no '
        'hardware or physical authority.'
    )
    drive=b'drive'; virtual=b'virtual'; robot=b'robot'
    paths={name:tmp_path/name for name in (
        'request.json','review.json','manifest.json','plan.json','layout.json',
        'drive.json','virtual.json','import.json','robot.usda','receipt.json',
        'status.json',
    )}
    paths['drive.json'].write_bytes(drive)
    paths['virtual.json'].write_bytes(virtual)
    paths['robot.usda'].write_bytes(robot)
    import_receipt={'value':1}
    import_receipt['receipt_sha256']=mechanics._canonical_sha256(import_receipt)
    paths['import.json'].write_text(json.dumps(import_receipt))
    manifest={'manifest_sha256':'a'*64}
    plan={'plan_sha256':'b'*64}
    for name,value in (
        ('review.json',{}),('manifest.json',manifest),('plan.json',plan),
        ('layout.json',{}),
    ):
        paths[name].write_text(json.dumps(value))
    request={
        'episode_id':episode_id,
        'required_authorization_statement':authorization,
        'attempt_contract':{
            'maximum_attempt_count':1,
            'automatic_retry_allowed':False,
            'fresh_runtime_file_revalidation_required':True,
            'hardware_or_physical_authority_allowed':False,
        },
        'native_replay_authorized':False,
        'mechanics_replays_executed':0,
        'runtime_files':{
            'key_mechanics_profile':{'sha256':'c'*64},
            'drive_profile':{'sha256':hashlib.sha256(drive).hexdigest()},
            'virtual_profile':{'sha256':hashlib.sha256(virtual).hexdigest()},
            'robot_usd':{
                'sha256':hashlib.sha256(robot).hexdigest(),
                'size_bytes':len(robot),
            },
            'robot_import_receipt':{
                'sha256':import_receipt['receipt_sha256']
            },
        },
    }
    request['request_sha256']=mechanics._canonical_sha256(request)
    paths['request.json'].write_text(json.dumps(request))
    monkeypatch.setattr(
        mechanics,'build_state_policy_fixed_fixture_single_replay_request',
        lambda *args:request,
    )
    monkeypatch.setattr(
        mechanics,'build_profile',lambda path:{'profile_sha256':'c'*64}
    )
    calls=[]
    def replay(**kwargs):
        calls.append(kwargs)
        return {
            'schema':mechanics.STATE_POLICY_NATIVE_MECHANICS_RECEIPT_SCHEMA,
            'episode_id':episode_id,
            'source_manifest_sha256':'a'*64,
            'source_plan_sha256':'b'*64,
            'source_single_replay_request_sha256':request['request_sha256'],
            'automatic_retry_performed':False,
            'hardware_access':False,
            'physical_authority':False,
        }
    monkeypatch.setattr(mechanics,'run_drive_controlled_robot_h_replay',replay)
    result=mechanics.run_state_policy_fixed_fixture_single_replay(
        request_path=paths['request.json'],
        authorization_statement=authorization,
        correction_review_path=paths['review.json'],
        corrected_manifest_path=paths['manifest.json'],
        replay_plan_path=paths['plan.json'],
        layout_path=paths['layout.json'],
        drive_profile_path=paths['drive.json'],
        virtual_profile_path=paths['virtual.json'],
        robot_import_receipt_path=paths['import.json'],
        robot_usd_path=paths['robot.usda'],
        output_path=paths['receipt.json'],status_path=paths['status.json'],
    )
    assert len(calls)==1
    assert result['source_single_replay_request_sha256']==request['request_sha256']

    with pytest.raises(mechanics.MechanicsContractError,match='authorization boundary'):
        mechanics.run_state_policy_fixed_fixture_single_replay(
            request_path=paths['request.json'],authorization_statement='wrong',
            correction_review_path=paths['review.json'],
            corrected_manifest_path=paths['manifest.json'],
            replay_plan_path=paths['plan.json'],layout_path=paths['layout.json'],
            drive_profile_path=paths['drive.json'],
            virtual_profile_path=paths['virtual.json'],
            robot_import_receipt_path=paths['import.json'],
            robot_usd_path=paths['robot.usda'],output_path=paths['receipt.json'],
            status_path=paths['status.json'],
        )
    assert len(calls)==1


def _arm234_synthetic_review_sources():
    mechanics=_load_key_mechanics()
    phases=(
        'PARK','TRANSIT','TRANSIT','TRANSIT','TRANSIT','HOVER',
        'CONTACT','RETRACT','HOVER','CONTACT','RETRACT',
    )
    source_plan={
        'schema':mechanics.STATE_POLICY_FIXED_FIXTURE_NATIVE_MECHANICS_REPLAY_PLAN_SCHEMA,
        'status':'READY_FOR_INDEPENDENT_FIXED_FIXTURE_CORRECTION_REVIEW',
        'fixed_fixture_correction_applied':True,
        'fixed_fixture_configuration':{
            'fixed_joint_enabled_explicitly':True,
            'solver_position_iteration_count':64,
            'solver_velocity_iteration_count':8,
        },
        'episode_id':'episode-test','target_id':'SPACE','sample_count':11,
        'contact_endpoint_sequences':[6,9],
        'joint_targets':[
            {
                'sequence':sequence,'phase':phase,
                'joint_position_target_rad':[0.0]*6,
            }
            for sequence,phase in enumerate(phases)
        ],
    }
    source_plan['plan_sha256']=mechanics._canonical_sha256(source_plan)
    trace=[
        {'target_sequence':0,'phase':'PARK','key_center_z_m':0.018},
        {'target_sequence':1,'phase':'TRANSIT','key_center_z_m':0.018},
        {'target_sequence':2,'phase':'TRANSIT','key_center_z_m':0.0177},
        {'target_sequence':3,'phase':'TRANSIT','key_center_z_m':0.016},
        {'target_sequence':4,'phase':'TRANSIT','key_center_z_m':0.0143},
    ]
    roots=[
        {
            'sequence':sequence,'orientation_delta_deg':orientation,
            'orientation_tolerance_deg':0.1,'translation_delta_mm':0.004,
            'translation_tolerance_mm':0.05,'passed':orientation<=0.1,
        }
        for sequence,orientation in enumerate((0.01,0.04,0.04,0.06,0.11))
    ]
    receipt={
        'schema':mechanics.STATE_POLICY_NATIVE_MECHANICS_RECEIPT_SCHEMA,
        'status':'BLOCKED_STATE_POLICY_NATIVE_MECHANICS_REPLAY',
        'failure_reason':'ROOT_INVARIANT','complete':False,
        'native_trace_retained':True,'automatic_retry_performed':False,
        'hardware_access':False,'physical_authority':False,
        'native_trace':trace,'native_trace_row_count':5,
        'attempted_joint_target_count':5,
        'root_pose_invariant':{
            'observations':roots,'observation_count':5,'all_passed':False,
        },
        'joint_tracking':[{} for _ in trace],
        'stopped_at_sequence':4,'stopped_phase':'TRANSIT',
        'episode_id':'episode-test','target_id':'SPACE',
        'source_plan_sha256':source_plan['plan_sha256'],
    }
    receipt['receipt_sha256']=mechanics._canonical_sha256(receipt)
    review=mechanics.review_state_policy_premature_transit_contact(receipt)
    return mechanics,source_plan,receipt,review


def test_arm234_reviews_premature_transit_displacement_offline():
    mechanics,_,receipt,first=_arm234_synthetic_review_sources()
    second=mechanics.review_state_policy_premature_transit_contact(receipt)
    assert first==second
    assert first['status']=='REVIEWED_PREMATURE_TRANSIT_KEY_DISPLACEMENT'
    assert first['first_material_transit_key_displacement']['sequence']==2
    assert first['first_root_orientation_rise']['sequence']==3
    assert first['fail_closed_stop']['sequence']==4
    assert first['temporal_separation']=={
        'displacement_to_orientation_rise_samples':1,
        'displacement_to_fail_closed_stop_samples':2,
    }
    assert first['review_decision'][
        'material_key_displacement_during_transit_confirmed'
    ] is True
    assert first['review_decision']['causality_proven'] is False
    assert first['review_decision']['another_replay_authorized'] is False
    assert first['isaac_started'] is first['physical_authority'] is False

    changed=json.loads(json.dumps(receipt))
    changed['hardware_access']=True
    changed.pop('receipt_sha256')
    changed['receipt_sha256']=mechanics._canonical_sha256(changed)
    with pytest.raises(mechanics.MechanicsContractError,match='boundary changed'):
        mechanics.review_state_policy_premature_transit_contact(changed)


def test_arm235_plans_bounded_offline_transit_clearance_correction():
    mechanics,source_plan,receipt,review=_arm234_synthetic_review_sources()
    first=mechanics.build_state_policy_transit_clearance_correction_plan(
        review,receipt,source_plan
    )
    second=mechanics.build_state_policy_transit_clearance_correction_plan(
        review,receipt,source_plan
    )
    assert first==second
    assert first['schema']==(
        mechanics.STATE_POLICY_TRANSIT_CLEARANCE_CORRECTION_PLAN_SCHEMA
    )
    assert first['correction_window']=={
        'last_preserved_pre_correction_sequence':1,
        'first_sequence_to_regenerate':2,
        'last_sequence_to_regenerate':5,
        'first_preserved_contact_sequence':6,
        'allowed_source_phases':['TRANSIT','HOVER'],
    }
    contract=first['materialization_contract']
    assert contract['minimum_noncontact_tool_key_clearance_mm']==0.5
    assert contract['maximum_noncontact_key_displacement_mm']==0.05
    assert contract['preserve_contact_endpoint_sequences'] is True
    assert contract['preserve_contact_endpoint_joint_targets'] is True
    assert first['corrected_joint_targets_materialized'] is False
    assert first['native_replay_authorized'] is False
    assert first['isaac_started'] is first['physical_authority'] is False

    changed=json.loads(json.dumps(source_plan))
    changed['joint_targets'][6]['phase']='HOVER'
    changed.pop('plan_sha256')
    changed['plan_sha256']=mechanics._canonical_sha256(changed)
    changed_receipt=json.loads(json.dumps(receipt))
    changed_receipt['source_plan_sha256']=changed['plan_sha256']
    changed_receipt.pop('receipt_sha256')
    changed_receipt['receipt_sha256']=mechanics._canonical_sha256(changed_receipt)
    changed_review=mechanics.review_state_policy_premature_transit_contact(
        changed_receipt
    )
    with pytest.raises(mechanics.MechanicsContractError,match='window changed'):
        mechanics.build_state_policy_transit_clearance_correction_plan(
            changed_review,changed_receipt,changed
        )


def test_arm236_blocks_reuse_of_noncontact_route_that_compresses_key():
    mechanics,source_plan,receipt,_=_arm234_synthetic_review_sources()
    for row in source_plan['joint_targets']:
        row['source_target_sequence']=27+row['sequence']
    source_plan.pop('plan_sha256')
    source_plan['plan_sha256']=mechanics._canonical_sha256(source_plan)
    receipt['source_plan_sha256']=source_plan['plan_sha256']
    receipt.pop('receipt_sha256')
    receipt['receipt_sha256']=mechanics._canonical_sha256(receipt)
    review=mechanics.review_state_policy_premature_transit_contact(receipt)
    correction=mechanics.build_state_policy_transit_clearance_correction_plan(
        review,receipt,source_plan
    )
    representative_plan={
        'target_id':'SPACE',
        'joint_targets':[{'sequence':sequence} for sequence in range(29,33)],
    }
    representative_plan['plan_sha256']=mechanics._canonical_sha256(
        representative_plan
    )
    native_trace=[]
    for sequence,separation_mm,key_z_m in (
        (29,22.0,0.018),(30,7.0,0.018),(31,0.004,0.01784),
        (32,0.004,0.01780),
    ):
        native_trace.append({
            'target_sequence':sequence,
            'tip_key_separation_m':separation_mm/1000.0,
            'key_center_z_m':key_z_m,
        })
    representative_receipt={
        'target_id':'SPACE',
        'source_plan_sha256':representative_plan['plan_sha256'],
        'native_trace':native_trace,
    }
    representative_receipt['receipt_sha256']=mechanics._canonical_sha256(
        representative_receipt
    )

    first=mechanics.review_state_policy_transit_clearance_materialization_readiness(
        correction,source_plan,representative_plan,representative_receipt
    )
    second=mechanics.review_state_policy_transit_clearance_materialization_readiness(
        correction,source_plan,representative_plan,representative_receipt
    )
    assert first==second
    assert first['status']==(
        'BLOCKED_SOURCE_ROUTE_VIOLATES_NONCONTACT_CONTRACT'
    )
    assert first['audited_source_target_sequences']==[29,30,31,32]
    assert first['failing_source_target_sequences']==[31,32]
    assert first['source_route_reusable'] is False
    assert first['materialization_decision'][
        'generate_new_lifted_board_frame_route'
    ] is True
    assert first['corrected_joint_targets_materialized'] is False
    assert first['continuous_clearance_proven'] is False
    assert first['isaac_started'] is first['physical_authority'] is False

    changed=json.loads(json.dumps(representative_receipt))
    changed['target_id']='H'
    changed.pop('receipt_sha256')
    changed['receipt_sha256']=mechanics._canonical_sha256(changed)
    with pytest.raises(mechanics.MechanicsContractError,match='lineage changed'):
        mechanics.review_state_policy_transit_clearance_materialization_readiness(
            correction,source_plan,representative_plan,changed
        )


def test_arm226_partial_failure_progress_retains_stop_metadata_and_counts():
    mechanics,sources,runtime=_arm222_compilation_sources()
    mechanics_campaign,plans=(
        mechanics.compile_state_policy_mechanics_replay_campaign(*sources)
    )
    admission_campaign,admissions=(
        mechanics.admit_state_policy_mechanics_runtime_inputs(
            mechanics_campaign,plans,*runtime
        )
    )
    _,native_plans=mechanics.materialize_state_policy_native_mechanics_inputs(
        admission_campaign,admissions,mechanics_campaign,plans
    )
    plan=next(iter(native_plans.values()))
    progress=mechanics.build_state_policy_native_execution_progress(
        plan=plan,
        attempted_joint_target_count=2,
        native_trace_row_count=7,
        failure_reason='ROOT_INVARIANT',
        stopped_target=plan['joint_targets'][1],
    )
    assert progress=={
        'complete':False,
        'failure_reason':'ROOT_INVARIANT',
        'stopped_at_sequence':1,
        'stopped_phase':'CONTACT',
        'stopped_action_index':1,
        'planned_joint_target_count':2,
        'attempted_joint_target_count':2,
        'native_trace_row_count':7,
        'native_trace_retained':True,
        'automatic_retry_performed':False,
    }


def test_arm226_complete_progress_requires_full_target_denominator():
    mechanics,sources,runtime=_arm222_compilation_sources()
    mechanics_campaign,plans=(
        mechanics.compile_state_policy_mechanics_replay_campaign(*sources)
    )
    admission_campaign,admissions=(
        mechanics.admit_state_policy_mechanics_runtime_inputs(
            mechanics_campaign,plans,*runtime
        )
    )
    _,native_plans=mechanics.materialize_state_policy_native_mechanics_inputs(
        admission_campaign,admissions,mechanics_campaign,plans
    )
    plan=next(iter(native_plans.values()))
    with pytest.raises(
        mechanics.MechanicsContractError,match='complete execution progress'
    ):
        mechanics.build_state_policy_native_execution_progress(
            plan=plan,
            attempted_joint_target_count=1,
            native_trace_row_count=3,
        )
