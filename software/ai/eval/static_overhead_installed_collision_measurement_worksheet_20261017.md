# Installed collision measurement worksheet

- Base contract SHA-256: `fe86a921dc05c406eef9d052efd77274e795e4d64eb873ea539afae3386d6d39`
- Root frame: `board`
- Required bodies: 19
- Status: `UNMEASURED_TEMPLATE`
- Authority: no profile, collision result, command, or physical authority

Record source hashes, methods, instruments, timestamps, millimetre-valued conservative envelopes, and uncertainty in the manifest. Do not fill unknown values with nominal dimensions.

| Body ID | Parent frame | Role | Binding mode | Required capture |
| --- | --- | --- | --- | --- |
| `robot:base_link` | `base_link` | `ROBOT_LINK` | `RIGID_FRAME` | measured conservative envelope and uncertainty |
| `robot:link1` | `link1` | `ROBOT_LINK` | `RIGID_FRAME` | measured conservative envelope and uncertainty |
| `robot:link2` | `link2` | `ROBOT_LINK` | `RIGID_FRAME` | measured conservative envelope and uncertainty |
| `robot:link3` | `link3` | `ROBOT_LINK` | `RIGID_FRAME` | measured conservative envelope and uncertainty |
| `robot:link4` | `link4` | `ROBOT_LINK` | `RIGID_FRAME` | measured conservative envelope and uncertainty |
| `robot:link5` | `link5` | `ROBOT_LINK` | `RIGID_FRAME` | measured conservative envelope and uncertainty |
| `robot:gripper` | `gripper_link` | `ROBOT_LINK` | `RIGID_FRAME` | measured conservative envelope and uncertainty |
| `installation:base_and_factory_clamp` | `board` | `BASE_CLAMP` | `STATIC_ROOT` | measured conservative envelope and uncertainty |
| `installation:static_camera_support` | `board` | `ATTACHMENT` | `STATIC_ROOT` | measured conservative envelope and uncertainty |
| `installation:static_camera_module` | `board` | `CAMERA` | `STATIC_ROOT` | measured conservative envelope and uncertainty |
| `installation:static_camera_connector` | `board` | `CONNECTOR` | `STATIC_ROOT` | measured conservative envelope and uncertainty |
| `installation:static_camera_cable` | `board` | `CABLE` | `STATIC_ROOT` | measured conservative envelope and uncertainty |
| `attachment:contact_tool` | `hand_tcp` | `TOOL` | `RIGID_FRAME` | measured conservative envelope and uncertainty |
| `workcell:board_solid` | `board` | `STATIC_ENVIRONMENT` | `STATIC_ROOT` | measured conservative envelope and uncertainty |
| `workcell:keyboard` | `board` | `STATIC_ENVIRONMENT` | `STATIC_ROOT` | measured conservative envelope and uncertainty |
| `workcell:phone` | `board` | `STATIC_ENVIRONMENT` | `STATIC_ROOT` | measured conservative envelope and uncertainty |
| `workcell:station:keyboard_left` | `board` | `STATIC_ENVIRONMENT` | `STATIC_ROOT` | measured conservative envelope and uncertainty |
| `workcell:station:keyboard_right` | `board` | `STATIC_ENVIRONMENT` | `STATIC_ROOT` | measured conservative envelope and uncertainty |
| `workcell:station:phone_tcp` | `board` | `STATIC_ENVIRONMENT` | `STATIC_ROOT` | measured conservative envelope and uncertainty |

## Clearance evidence

Record the reviewed minimum separation, geometry uncertainty per body, pose uncertainty per body, and their source hashes. An all-zero or unsourced policy is rejected.

This worksheet is read-only planning output. It does not qualify geometry.
