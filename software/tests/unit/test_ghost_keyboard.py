import json
import hashlib
import importlib.util
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
        'rotation_row_major':[1.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,1.0],
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

    receipt['samples'][0]['source_segment_index']=1
    receipt['receipt_sha256']=mechanics._canonical_sha256({
        key:value for key,value in receipt.items() if key!='receipt_sha256'
    })
    with pytest.raises(mechanics.MechanicsContractError,match='sample lineage'):
        mechanics.build_collision_blocker_localization(receipt,request,cartesian)
