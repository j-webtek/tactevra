import json
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
