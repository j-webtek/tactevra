import argparse, hashlib, json, math, xml.etree.ElementTree as ET
from pathlib import Path
from pxr import Usd, UsdPhysics

parser = argparse.ArgumentParser(description='Compare authored USD joint frames with the governed URDF')
parser.add_argument('--usd', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[3]
urdf = root / 'software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf'
usd = args.usd
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
if sha(urdf) != 'a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190' or sha(usd) != 'a0ec437fb4d647f354007dc352a3af8b13576eaf4931d69d60a510bf235ebea2':
    raise ValueError('asset digest mismatch')
stage = Usd.Stage.Open(str(usd))
if not stage: raise ValueError('could not open USD')
rows = []
for joint in ET.parse(urdf).getroot().findall('joint'):
    if joint.get('type') != 'revolute': continue
    name = joint.get('name')
    prim = stage.GetPrimAtPath('/roarm_m3/Physics/' + name)
    if not prim.IsA(UsdPhysics.RevoluteJoint): raise ValueError(name + ': missing joint')
    j = UsdPhysics.RevoluteJoint(prim)
    body0, body1 = j.GetBody0Rel().GetTargets(), j.GetBody1Rel().GetTargets()
    if len(body0) != 1 or len(body1) != 1 or body0[0].name != joint.find('parent').get('link') or body1[0].name != joint.find('child').get('link'):
        raise ValueError(name + ': body mismatch')
    xyz = [float(v) for v in joint.find('origin').get('xyz').split()]
    r,p,y = [float(v) for v in joint.find('origin').get('rpy').split()]
    cr,sr,cp,sp,cy,sy = math.cos(r/2),math.sin(r/2),math.cos(p/2),math.sin(p/2),math.cos(y/2),math.sin(y/2)
    q = [cr*cp*cy+sr*sp*sy, sr*cp*cy-cr*sp*sy, cr*sp*cy+sr*cp*sy, cr*cp*sy-sr*sp*cy]
    q0, q1 = j.GetLocalRot0Attr().Get(), j.GetLocalRot1Attr().Get()
    actual = [q0.GetReal(), *q0.GetImaginary()]
    dot = abs(sum(a*b for a,b in zip(q,actual))) / math.sqrt(sum(a*a for a in actual))
    rotation_error = 2 * math.acos(min(1.0, max(0.0, dot)))
    p0, p1 = j.GetLocalPos0Attr().Get(), j.GetLocalPos1Attr().Get()
    error = max(abs(float(a)-b) for a,b in zip(p0,xyz))
    if error > 1e-7 or rotation_error > 1e-6 or max(map(abs,p1)) > 1e-9 or abs(q1.GetReal()-1) > 1e-9 or max(map(abs,q1.GetImaginary())) > 1e-9 or j.GetAxisAttr().Get() != 'Z' or joint.find('axis').get('xyz') != '0 0 1':
        raise ValueError(name + ': frame or axis mismatch')
    rows.append({'joint': name, 'translation_max_error_m': error, 'rotation_error_rad': rotation_error})
if len(rows) != 6: raise ValueError('joint inventory mismatch')
receipt = {'usd_sha256':sha(usd),'urdf_sha256':sha(urdf),'joint_comparisons':rows,
           'scope':'authored USD joint frames against URDF; no live physics articulation',
           'isaac_started':False,'hardware_access':False,
           'verifier_sha256':sha(Path(__file__))}
receipt['receipt_sha256'] = hashlib.sha256(json.dumps(receipt,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
out = args.output
with out.open('x',encoding='utf8') as f: json.dump(receipt,f,indent=2,sort_keys=True)
print(json.dumps(receipt))
