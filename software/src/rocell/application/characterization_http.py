"""Authenticated no-retry LAN transport. Construction performs no I/O.

Live reviewed-hover framing is opt-in; no live CLI or runner is exposed here.
Verify installed compatibility and a fresh boot before use.
"""
import math
import re
import socket
import time
from .servo_diagnostic_http import DiagnosticHTTPReader
from .characterization_http_session import CharacterizationHTTPSession
from .reviewed_hover_manifest import decode_reviewed_hover_start
from .reviewed_hover_manifest import ghost_key_manifest, validate_manifest
from .reviewed_hover_live_admission import decode_live_admission
from .reviewed_hover_recovery_admission import decode_recovery_admission


class CharacterizationHTTP:
    def __init__(self,address,port=80,*,key,boot,read_only_initial_sequence=0,
                 reviewed_hover_live_release_sha256=None,
                 recovery_hover_live_release_sha256=None,
                 registration_ladder_release_sha256=None):
        checked=DiagnosticHTTPReader(address,port)
        self.address,self.port=checked.address,checked.port
        if (type(read_only_initial_sequence) is not int or
                not 0 <= read_only_initial_sequence < 4096):
            raise ValueError('Invalid authenticated sequence')
        self.read_only_only=read_only_initial_sequence != 0
        if (reviewed_hover_live_release_sha256 is not None and
                (type(reviewed_hover_live_release_sha256) is not str or
                 not re.fullmatch(r'[0-9a-f]{64}', reviewed_hover_live_release_sha256) or
                 reviewed_hover_live_release_sha256 == '0'*64 or
                 self.read_only_only)):
            raise ValueError('Fresh exact reviewed-hover live release required')
        self.reviewed_hover_live_release_sha256=reviewed_hover_live_release_sha256
        if (recovery_hover_live_release_sha256 is not None and
                (type(recovery_hover_live_release_sha256) is not str or
                 not re.fullmatch(r'[0-9a-f]{64}', recovery_hover_live_release_sha256) or
                 recovery_hover_live_release_sha256 == '0'*64 or
                 self.read_only_only or
                 reviewed_hover_live_release_sha256 is not None)):
            raise ValueError('Fresh exclusive recovery-hover release required')
        self.recovery_hover_live_release_sha256=recovery_hover_live_release_sha256
        if (registration_ladder_release_sha256 is not None and
                (type(registration_ladder_release_sha256) is not str or
                 not re.fullmatch(r'[0-9a-f]{64}', registration_ladder_release_sha256) or
                 registration_ladder_release_sha256 == '0'*64 or
                 self.read_only_only or reviewed_hover_live_release_sha256 is not None or
                 recovery_hover_live_release_sha256 is not None)):
            raise ValueError('Fresh exclusive registration-ladder release required')
        self.registration_ladder_release_sha256=registration_ladder_release_sha256
        self.session=CharacterizationHTTPSession(key=key,boot=boot)
        # Reconcile a known prior signed request sequence without creating a
        # new write authority. Only GETs are possible on this instance.
        self.session._sequence=read_only_initial_sequence

    def __call__(self,method,path,body=b'',timeout=3):
        try:
            if self.read_only_only and method!='GET':
                raise ValueError('Sequence-resumed transport is read-only')
            routes={'prepare':'POST','status':'GET','challenge':'GET','start':'POST',
                    'receipt':'POST','record-info':'GET','record-chunk':'POST','fault':'GET','reference':'GET'}
            reanchor={'start':'POST','status':'GET','record':'GET','receipt':'POST'}
            park_step={'start':'POST','status':'GET','record':'GET','receipt':'POST'}
            park_return={'start':'POST','status':'GET','record':'GET','receipt':'POST'}
            large_pose_lift={'start':'POST','status':'GET','record':'GET','receipt':'POST'}
            large_pose_relief={'start':'POST','status':'GET','record':'GET','receipt':'POST'}
            prefix='/rocell/characterization/'
            fixed_prefix='/rocell/reanchor/'
            park_prefix='/rocell/park-step/'
            return_prefix='/rocell/park-return/'
            lift_prefix='/rocell/large-pose-lift/'
            relief_prefix='/rocell/large-pose-relief/'
            repeat_prefix='/rocell/p4-repeat/'
            correction_prefix='/rocell/p4-correction/'
            midpoint_prefix='/rocell/p4-midpoint/'
            air_prefix='/rocell/air-type/'
            b_hover_prefix='/rocell/air-type-b-hover/'
            finale_prefix='/rocell/air-type-final/'
            last_prefix='/rocell/air-type-last/'
            repeat_air_prefix='/rocell/air-type-repeat/'
            elbow_direction_prefix='/rocell/air-elbow-direction/'
            elbow_shift_prefix='/rocell/air-elbow-shift/'
            elbow_grid_prefix='/rocell/air-elbow-grid/'
            multi_hover_prefix='/rocell/air-multi-hover/'
            reviewed_hover_prefix='/rocell/reviewed-hover/'
            recovery_hover_prefix='/rocell/recovery-hover/'
            registration_ladder_prefix='/rocell/registration-ladder/'
            repeating=type(path) is str and path.startswith(repeat_prefix)
            correcting=type(path) is str and path.startswith(correction_prefix)
            midpoint=type(path) is str and path.startswith(midpoint_prefix)
            air=type(path) is str and path.startswith(air_prefix)
            b_hover=type(path) is str and path.startswith(b_hover_prefix)
            finale=type(path) is str and path.startswith(finale_prefix)
            last=type(path) is str and path.startswith(last_prefix)
            repeat_air=type(path) is str and path.startswith(repeat_air_prefix)
            elbow_direction=type(path) is str and path.startswith(elbow_direction_prefix)
            elbow_shift=type(path) is str and path.startswith(elbow_shift_prefix)
            elbow_grid=type(path) is str and path.startswith(elbow_grid_prefix)
            multi_hover=type(path) is str and path.startswith(multi_hover_prefix)
            reviewed_hover=type(path) is str and path.startswith(reviewed_hover_prefix)
            recovery_hover=type(path) is str and path.startswith(recovery_hover_prefix)
            registration_ladder=(type(path) is str and
                                 path.startswith(registration_ladder_prefix))
            fixed=type(path) is str and path.startswith(fixed_prefix)
            park=type(path) is str and path.startswith(park_prefix)
            returning=type(path) is str and path.startswith(return_prefix)
            lifting=type(path) is str and path.startswith(lift_prefix)
            relieving=type(path) is str and path.startswith(relief_prefix)
            suffix=(path[len(registration_ladder_prefix):] if registration_ladder else
                    path[len(recovery_hover_prefix):] if recovery_hover else
                    path[len(reviewed_hover_prefix):] if reviewed_hover else
                    path[len(multi_hover_prefix):] if multi_hover else
                    path[len(elbow_grid_prefix):] if elbow_grid else
                    path[len(elbow_shift_prefix):] if elbow_shift else
                    path[len(elbow_direction_prefix):] if elbow_direction else
                    path[len(repeat_air_prefix):] if repeat_air else
                    path[len(last_prefix):] if last else
                    path[len(finale_prefix):] if finale else
                    path[len(b_hover_prefix):] if b_hover else
                    path[len(air_prefix):] if air else
                    path[len(midpoint_prefix):] if midpoint else
                    path[len(correction_prefix):] if correcting else
                    path[len(repeat_prefix):] if repeating else path[len(relief_prefix):] if relieving else
                    path[len(lift_prefix):] if lifting else
                    path[len(return_prefix):] if returning else
                    path[len(park_prefix):] if park else
                    path[len(fixed_prefix):] if fixed else
                    path[len(prefix):] if type(path) is str and path.startswith(prefix) else '')
            if ((dict(leg='POST',status='GET') if registration_ladder else dict(start='POST',status='GET',record='GET',receipt='POST',next='POST') if reviewed_hover or recovery_hover else dict(start='POST',status='GET',record='GET',receipt='POST') if b_hover else dict(start='POST',status='GET',record='GET',receipt='POST',next='POST',**({'source-fault':'GET'} if last or repeat_air or elbow_direction or elbow_shift or elbow_grid or multi_hover else {})) if repeating or correcting or midpoint or air or finale or last or repeat_air or elbow_direction or elbow_shift or elbow_grid or multi_hover else large_pose_relief if relieving else large_pose_lift if lifting else park_return if returning else park_step if park else reanchor if fixed else routes).get(suffix)!=method or type(body) is not bytes
                    or type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=3):
                raise ValueError('Unsupported campaign request')
            if method=='GET' or suffix=='prepare' or ((fixed or returning) and suffix=='start'):
                if body:raise ValueError('Body not allowed')
            elif registration_ladder:
                if suffix == 'leg':
                    if self.registration_ladder_release_sha256 is None:
                        raise ValueError('Exact registration-ladder release required')
                    expected=(b'RCLW1:'+self.session._boot.encode('ascii')+b':1:'+
                              self.registration_ladder_release_sha256.encode('ascii')+
                              b':LIVE_NONCONTACT')
                    if body != expected:
                        raise ValueError('Exact registration-ladder admission required')
            elif recovery_hover:
                if suffix=='start':
                    if self.recovery_hover_live_release_sha256 is None:
                        raise ValueError('Exact recovery-hover release required')
                    decode_recovery_admission(body,boot=self.session._boot,
                        release_sha256=self.recovery_hover_live_release_sha256)
                elif suffix=='next' and not re.fullmatch(rb'[2-5]',body):
                    raise ValueError('Exact recovery-hover next leg required')
                elif suffix=='receipt' and not re.fullmatch(rb'[1-5]:[0-9a-f]{64}',body):
                    raise ValueError('Exact recovery-hover receipt required')
            elif reviewed_hover:
                if suffix=='start':
                    if self.reviewed_hover_live_release_sha256 is None:
                        if self.address != '127.0.0.1':
                            raise ValueError('Offline reviewed-hover selector is loopback-only')
                        decode_reviewed_hover_start(body)
                    else:
                        decoded=decode_live_admission(body,boot=self.session._boot,
                            release_sha256=self.reviewed_hover_live_release_sha256)
                        expected=validate_manifest(ghost_key_manifest())['manifest_sha256']
                        if decoded['recipe_sha256']!=expected:
                            raise ValueError('Exact reviewed-hover live recipe required')
                elif suffix=='next' and not re.fullmatch(rb'(?:[2-9]|1[0-6])',body):
                    raise ValueError('Exact reviewed-hover next leg required')
                elif suffix=='receipt' and not re.fullmatch(rb'(?:[1-9]|1[0-6]):[0-9a-f]{64}',body):
                    raise ValueError('Exact reviewed-hover receipt required')
            elif repeating or correcting or midpoint or air or b_hover or finale or last or repeat_air or elbow_direction or elbow_shift or elbow_grid or multi_hover:
                selector=b'AIRM5' if multi_hover else b'AIRG16' if elbow_grid else b'AIRH8' if elbow_shift else b'AIRE8' if elbow_direction else b'AIR6' if repeat_air else b'AIR4' if last else b'AIR7' if finale else b'AIRB1' if b_hover else b'AIR17' if air else b'P4M16' if midpoint else b'P4C16' if correcting else b'P4R12'
                ordinal=rb'[2-5]' if multi_hover else rb'(?:[2-9]|1[0-6])' if elbow_grid else rb'[2-8]' if elbow_shift or elbow_direction else rb'[2-6]' if repeat_air else rb'[2-4]' if last else rb'[2-7]' if finale else rb'(?:[2-9]|1[0-7])' if air else rb'(?:[2-9]|1[0-6])' if correcting or midpoint else rb'(?:[2-9]|1[0-2])'
                receipt=rb'[1-5]:[0-9a-f]{64}' if multi_hover else rb'(?:[1-9]|1[0-6]):[0-9a-f]{64}' if elbow_grid else rb'[1-8]:[0-9a-f]{64}' if elbow_shift or elbow_direction else rb'[1-6]:[0-9a-f]{64}' if repeat_air else rb'[1-4]:[0-9a-f]{64}' if last else rb'[1-7]:[0-9a-f]{64}' if finale else rb'1:[0-9a-f]{64}' if b_hover else rb'(?:[1-9]|1[0-7]):[0-9a-f]{64}' if air else rb'(?:[1-9]|1[0-6]):[0-9a-f]{64}' if correcting or midpoint else rb'(?:[1-9]|1[0-2]):[0-9a-f]{64}'
                if suffix=='start' and body!=selector:
                    raise ValueError('Exact '+selector.decode()+' selector required')
                if suffix=='next' and not re.fullmatch(ordinal,body):
                    raise ValueError('Exact next leg required')
                if suffix=='receipt' and not re.fullmatch(receipt,body):
                    raise ValueError('Exact leg and digest receipt required')
            elif park and suffix=='start':
                if not re.fullmatch(rb'[0-9]{4},[0-9]{4}', body):
                    raise ValueError('Bounded park-step targets required')
            elif lifting and suffix=='start':
                if body!=b'T1':
                    raise ValueError('Exact T1 selector required')
            elif relieving and suffix=='start':
                if body not in (b'P1', b'P2L', b'P2', b'P3E', b'P3', b'T4L', b'T4', b'P4E', b'P4'):
                    raise ValueError('Exact reviewed pose selector required')
            elif not re.fullmatch(rb'[0-9a-f]+',body) or len(body)%2 or len(body)>1024:
                raise ValueError('Bounded hexadecimal body required')
            if not (recovery_hover or reviewed_hover or repeating or correcting or midpoint or air or b_hover or finale or last or repeat_air or elbow_direction or elbow_shift or elbow_grid or multi_hover) and suffix=='receipt' and len(body)!=(64 if fixed or park or returning or lifting or relieving else 248):
                raise ValueError('Invalid receipt length')
            if not fixed and not returning and suffix=='record-chunk' and len(body)!=70:
                raise ValueError('Invalid chunk request length')
            request=self.session.request(method,path,body)
            deadline=time.monotonic()+timeout
            def remaining():
                value=deadline-time.monotonic()
                if value<=0:raise TimeoutError('Total HTTP deadline')
                return value
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as connection:
                connection.settimeout(remaining());connection.connect((self.address,self.port))
                headers=''.join(f'{k}: {v}\r\n' for k,v in request['headers'].items())
                wire=(f'{method} {path} HTTP/1.1\r\nHost: {self.address}:{self.port}\r\n'
                      f'Content-Length: {len(body)}\r\nContent-Type: text/plain\r\n'
                      f'{headers}Accept-Encoding: identity\r\nConnection: close\r\n\r\n').encode('ascii')+body
                connection.settimeout(remaining());connection.sendall(wire)
                def receive(count):
                    connection.settimeout(remaining());data=connection.recv(count);remaining()
                    if not data:raise ValueError('Truncated HTTP response')
                    return data
                header=bytearray()
                while not header.endswith(b'\r\n\r\n'):
                    if len(header)>=4096:raise ValueError('Header budget exceeded')
                    header.extend(receive(1))
                lines=bytes(header).decode('ascii').split('\r\n')
                match=re.fullmatch(r'HTTP/1\.[01] ([0-9]{3})(?: .*|)',lines[0])
                if not match:raise ValueError('Invalid HTTP status')
                fields={}
                for line in lines[1:-2]:
                    name,separator,value=line.partition(':');name=name.lower()
                    # ESP32 routes and their auth wrapper both emit no-store.
                    # Collapse only this exact harmless duplicate; never accept
                    # duplicate framing, sequence or signature headers.
                    if separator and name=='cache-control' and fields.get(name)=='no-store' and value.strip()=='no-store':
                        continue
                    if not separator or name in fields or name.strip()!=name:raise ValueError('Invalid or duplicate headers')
                    fields[name]=value.strip()
                if 'transfer-encoding' in fields or fields.get('content-encoding','identity')!='identity':
                    raise ValueError('Unsupported response encoding')
                length=fields.get('content-length','')
                if not re.fullmatch(r'0|[1-9][0-9]{0,3}',length) or int(length)>4095:
                    raise ValueError('Invalid response length')
                raw=bytearray()
                while len(raw)<int(length):raw.extend(receive(int(length)-len(raw)))
                return self.session.response(status=int(match[1]),body=bytes(raw),
                    sequence=fields.get('x-rocell-sequence'),signature=fields.get('x-rocell-signature'))
        except Exception:
            self.session.delivery_uncertain()
            raise
