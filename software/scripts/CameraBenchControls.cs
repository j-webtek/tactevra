// Camera-only bench observation. No filter graph, stream, Set call, serial or
// robot API is used. The parent runs this in a bounded disposable process.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

namespace RoCellBench {
    [ComImport, Guid("29840822-5B84-11D0-BD3B-00A0C911CE86"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface ICreateDevEnum {
        [PreserveSig] int CreateClassEnumerator(ref Guid category, out IEnumMoniker enumerator, int flags);
    }
    [ComImport, Guid("55272A00-42CB-11CE-8135-00AA004BB851"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPropertyBag {
        [PreserveSig] int Read([MarshalAs(UnmanagedType.LPWStr)] string name, [MarshalAs(UnmanagedType.Struct)] out object value, IntPtr errorLog);
        [PreserveSig] int Write([MarshalAs(UnmanagedType.LPWStr)] string name, [MarshalAs(UnmanagedType.Struct)] ref object value);
    }
    [ComImport, Guid("C6E13360-30AC-11D0-A18C-00A0C9118956"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAMVideoProcAmp {
        [PreserveSig] int GetRange(int property, out int min, out int max, out int step, out int def, out int flags);
        // This declaration preserves the COM vtable slot. It is never called.
        [PreserveSig] int Set(int property, int value, int flags);
        [PreserveSig] int Get(int property, out int value, out int flags);
    }
    [ComImport, Guid("C6E13370-30AC-11D0-A18C-00A0C9118956"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAMCameraControl {
        [PreserveSig] int GetRange(int property, out int min, out int max, out int step, out int def, out int flags);
        [PreserveSig] int Set(int property, int value, int flags);
        [PreserveSig] int Get(int property, out int value, out int flags);
    }
    public static class CameraBenchControls {
        static void Release(object value) {
            // A property bag can share a COM identity/RCW with its moniker.
            // Balance this acquisition only: FinalRelease invalidates other
            // still-owned interfaces on that shared wrapper.
            if (value != null && Marshal.IsComObject(value)) Marshal.ReleaseComObject(value);
        }
        static string Property(IMoniker moniker, string key) {
            object bag = null;
            try {
                Guid iid = typeof(IPropertyBag).GUID;
                moniker.BindToStorage(null, null, ref iid, out bag);
                object value;
                return ((IPropertyBag)bag).Read(key, out value, IntPtr.Zero) == 0 ? value as string : null;
            } finally { Release(bag); }
        }
        static Dictionary<string, object> Control(object filter, string name, int id, bool camera) {
            var row = new Dictionary<string, object>();
            row["name"] = name;
            row["interface"] = camera ? "IAMCameraControl" : "IAMVideoProcAmp";
            try {
                int min, max, step, def, capabilities, current, flags;
                int rangeResult, getResult;
                if (camera) {
                    var access = (IAMCameraControl)filter;
                    rangeResult = access.GetRange(id, out min, out max, out step, out def, out capabilities);
                    getResult = access.Get(id, out current, out flags);
                } else {
                    var access = (IAMVideoProcAmp)filter;
                    rangeResult = access.GetRange(id, out min, out max, out step, out def, out capabilities);
                    getResult = access.Get(id, out current, out flags);
                }
                row["range_hresult"] = rangeResult;
                row["get_hresult"] = getResult;
                row["range_observed"] = rangeResult == 0;
                row["value_observed"] = getResult == 0;
                if (rangeResult == 0) {
                    row["minimum"] = min; row["maximum"] = max; row["step"] = step;
                    row["default"] = def; row["capability_flags"] = capabilities;
                    row["manual_supported"] = (capabilities & 2) != 0;
                    row["auto_supported"] = (capabilities & 1) != 0;
                }
                if (getResult == 0) {
                    row["current_value"] = current; row["current_flags"] = flags;
                    row["reported_mode"] = flags == 1 ? "auto" : flags == 2 ? "manual" : "unknown_or_combined";
                }
            } catch (Exception error) {
                row["error"] = error.GetType().Name + ": " + error.Message;
            }
            return row;
        }
        static Dictionary<string, object> SetMode(object filter, string name, int id, int requested, int requestedFlags, bool camera) {
            if (requestedFlags != 1 && requestedFlags != 2)
                throw new ArgumentOutOfRangeException("requestedFlags");
            int min, max, step, def, capabilities, before, beforeFlags, after, afterFlags;
            int rangeResult, beforeResult, setResult, afterResult;
            if (camera) {
                var access = (IAMCameraControl)filter;
                rangeResult = access.GetRange(id, out min, out max, out step, out def, out capabilities);
                beforeResult = access.Get(id, out before, out beforeFlags);
                if (rangeResult != 0 || beforeResult != 0) throw new InvalidOperationException(name + " read failed.");
                if ((capabilities & requestedFlags) == 0 || requested < min || requested > max || (requested - min) % step != 0)
                    throw new ArgumentOutOfRangeException(name, "Requested control mode/value is unsupported.");
                setResult = access.Set(id, requested, requestedFlags);
                afterResult = access.Get(id, out after, out afterFlags);
            } else {
                var access = (IAMVideoProcAmp)filter;
                rangeResult = access.GetRange(id, out min, out max, out step, out def, out capabilities);
                beforeResult = access.Get(id, out before, out beforeFlags);
                if (rangeResult != 0 || beforeResult != 0) throw new InvalidOperationException(name + " read failed.");
                if ((capabilities & requestedFlags) == 0 || requested < min || requested > max || (requested - min) % step != 0)
                    throw new ArgumentOutOfRangeException(name, "Requested control mode/value is unsupported.");
                setResult = access.Set(id, requested, requestedFlags);
                afterResult = access.Get(id, out after, out afterFlags);
            }
            if (setResult != 0 || afterResult != 0 || afterFlags != requestedFlags ||
                (requestedFlags == 2 && after != requested))
                throw new InvalidOperationException(name + " control write/readback failed.");
            return new Dictionary<string, object> {
                {"name", name}, {"interface", camera ? "IAMCameraControl" : "IAMVideoProcAmp"},
                {"requested_value", requested}, {"before_value", before},
                {"before_flags", beforeFlags}, {"before_mode", beforeFlags == 1 ? "auto" : beforeFlags == 2 ? "manual" : "unknown_or_combined"},
                {"set_hresult", setResult}, {"after_value", after}, {"after_flags", afterFlags},
                {"after_mode", afterFlags == 1 ? "auto" : "manual"}, {"readback_matches", true}
            };
        }
        public static List<string> FindDevicePaths(string expectedName) {
            if (expectedName != "Arducam B0477 (USB3 20MP)")
                throw new ArgumentException("Exact observed B0477 selection required.");
            object system = null;
            IEnumMoniker enumeration = null;
            var paths = new List<string>();
            try {
                system = Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("62BE5D10-60EB-11D0-BD3B-00A0C911CE86")));
                Guid category = new Guid("860BB310-5D01-11D0-BD3B-00A0C911CE86");
                int hr = ((ICreateDevEnum)system).CreateClassEnumerator(ref category, out enumeration, 0);
                if (hr != 0 || enumeration == null) throw new InvalidOperationException("No video enumeration.");
                var next = new IMoniker[1];
                int count = 0;
                while (enumeration.Next(1, next, IntPtr.Zero) == 0) {
                    IMoniker item = next[0];
                    try {
                        if (++count > 32) throw new InvalidOperationException("Video inventory limit.");
                        if (Property(item, "FriendlyName") == expectedName) {
                            string path = Property(item, "DevicePath");
                            if (!String.IsNullOrEmpty(path)) paths.Add(path);
                        }
                    } finally { Release(item); }
                }
                return paths;
            } finally {
                Release(enumeration); Release(system);
            }
        }
        public static Dictionary<string, object> Read(string expectedName, string expectedDevicePath) {
            if (expectedName != "Arducam B0477 (USB3 20MP)" || String.IsNullOrEmpty(expectedDevicePath))
                throw new ArgumentException("Exact observed B0477 selection required.");
            object system = null, filter = null;
            IEnumMoniker enumeration = null;
            var matches = new List<IMoniker>();
            try {
                system = Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("62BE5D10-60EB-11D0-BD3B-00A0C911CE86")));
                Guid category = new Guid("860BB310-5D01-11D0-BD3B-00A0C911CE86");
                int hr = ((ICreateDevEnum)system).CreateClassEnumerator(ref category, out enumeration, 0);
                if (hr != 0 || enumeration == null) throw new InvalidOperationException("No video enumeration.");
                var next = new IMoniker[1];
                int count = 0;
                while (enumeration.Next(1, next, IntPtr.Zero) == 0) {
                    IMoniker item = next[0];
                    bool retain = false;
                    try {
                        if (++count > 32) throw new InvalidOperationException("Video inventory limit.");
                        retain = Property(item, "FriendlyName") == expectedName &&
                            String.Equals(Property(item, "DevicePath"), expectedDevicePath, StringComparison.OrdinalIgnoreCase);
                        if (retain) matches.Add(item);
                    } finally { if (!retain) Release(item); }
                }
                if (matches.Count != 1) throw new InvalidOperationException("Exact camera path is missing or ambiguous.");
                Guid baseFilter = new Guid("56A86895-0AD4-11CE-B03A-0020AF0BA770");
                matches[0].BindToObject(null, null, ref baseFilter, out filter);
                var controls = new List<Dictionary<string, object>>();
                controls.Add(Control(filter, "brightness", 0, false));
                controls.Add(Control(filter, "contrast", 1, false));
                controls.Add(Control(filter, "saturation", 3, false));
                controls.Add(Control(filter, "white_balance", 7, false));
                controls.Add(Control(filter, "gain", 9, false));
                controls.Add(Control(filter, "exposure", 4, true));
                controls.Add(Control(filter, "iris", 5, true));
                controls.Add(Control(filter, "focus", 6, true));
                return new Dictionary<string, object> {
                    {"schema", "rocell.camera_bench_control_observation.v1"},
                    {"device_name", expectedName}, {"device_path", expectedDevicePath},
                    {"controls", controls}, {"control_set_calls", 0}, {"streams_started", 0},
                    {"physical_commissioning_pass", false}, {"arm_access", false},
                    {"meaning", "Read-only DirectShow control observations. No write/readback or persistence qualification."}
                };
            } finally {
                Release(filter);
                foreach (var item in matches) Release(item);
                Release(enumeration); Release(system);
            }
        }
        public static Dictionary<string, object> LockExposureGainAndWhiteBalance(
            string expectedName, string expectedDevicePath, int exposure, int gain, int whiteBalance) {
            if (expectedName != "Arducam B0477 (USB3 20MP)" || String.IsNullOrEmpty(expectedDevicePath))
                throw new ArgumentException("Exact observed B0477 selection required.");
            object system = null, filter = null;
            IEnumMoniker enumeration = null;
            var matches = new List<IMoniker>();
            try {
                system = Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("62BE5D10-60EB-11D0-BD3B-00A0C911CE86")));
                Guid category = new Guid("860BB310-5D01-11D0-BD3B-00A0C911CE86");
                int hr = ((ICreateDevEnum)system).CreateClassEnumerator(ref category, out enumeration, 0);
                if (hr != 0 || enumeration == null) throw new InvalidOperationException("No video enumeration.");
                var next = new IMoniker[1];
                int count = 0;
                while (enumeration.Next(1, next, IntPtr.Zero) == 0) {
                    IMoniker item = next[0];
                    bool retain = false;
                    try {
                        if (++count > 32) throw new InvalidOperationException("Video inventory limit.");
                        retain = Property(item, "FriendlyName") == expectedName &&
                            String.Equals(Property(item, "DevicePath"), expectedDevicePath, StringComparison.OrdinalIgnoreCase);
                        if (retain) matches.Add(item);
                    } finally { if (!retain) Release(item); }
                }
                if (matches.Count != 1) throw new InvalidOperationException("Exact camera path is missing or ambiguous.");
                Guid baseFilter = new Guid("56A86895-0AD4-11CE-B03A-0020AF0BA770");
                matches[0].BindToObject(null, null, ref baseFilter, out filter);
                var changes = new List<Dictionary<string, object>>();
                changes.Add(SetMode(filter, "white_balance", 7, whiteBalance, 2, false));
                changes.Add(SetMode(filter, "gain", 9, gain, 2, false));
                changes.Add(SetMode(filter, "exposure", 4, exposure, 2, true));
                return new Dictionary<string, object> {
                    {"schema", "rocell.camera_bench_control_lock.v1"},
                    {"device_name", expectedName}, {"device_path", expectedDevicePath},
                    {"changes", changes}, {"control_set_calls", 3}, {"streams_started", 0},
                    {"arm_access", false}, {"camera_only", true},
                    {"meaning", "Exact camera-only manual-control write with immediate DirectShow readback."}
                };
            } finally {
                Release(filter);
                foreach (var item in matches) Release(item);
                Release(enumeration); Release(system);
            }
        }
        public static Dictionary<string, object> RestoreAutomaticExposureAndWhiteBalance(
            string expectedName, string expectedDevicePath, int exposure, int whiteBalance) {
            if (expectedName != "Arducam B0477 (USB3 20MP)" || String.IsNullOrEmpty(expectedDevicePath))
                throw new ArgumentException("Exact observed B0477 selection required.");
            object system = null, filter = null;
            IEnumMoniker enumeration = null;
            var matches = new List<IMoniker>();
            try {
                system = Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("62BE5D10-60EB-11D0-BD3B-00A0C911CE86")));
                Guid category = new Guid("860BB310-5D01-11D0-BD3B-00A0C911CE86");
                int hr = ((ICreateDevEnum)system).CreateClassEnumerator(ref category, out enumeration, 0);
                if (hr != 0 || enumeration == null) throw new InvalidOperationException("No video enumeration.");
                var next = new IMoniker[1];
                int count = 0;
                while (enumeration.Next(1, next, IntPtr.Zero) == 0) {
                    IMoniker item = next[0];
                    bool retain = false;
                    try {
                        if (++count > 32) throw new InvalidOperationException("Video inventory limit.");
                        retain = Property(item, "FriendlyName") == expectedName &&
                            String.Equals(Property(item, "DevicePath"), expectedDevicePath, StringComparison.OrdinalIgnoreCase);
                        if (retain) matches.Add(item);
                    } finally { if (!retain) Release(item); }
                }
                if (matches.Count != 1) throw new InvalidOperationException("Exact camera path is missing or ambiguous.");
                Guid baseFilter = new Guid("56A86895-0AD4-11CE-B03A-0020AF0BA770");
                matches[0].BindToObject(null, null, ref baseFilter, out filter);
                var changes = new List<Dictionary<string, object>>();
                changes.Add(SetMode(filter, "white_balance", 7, whiteBalance, 1, false));
                changes.Add(SetMode(filter, "exposure", 4, exposure, 1, true));
                return new Dictionary<string, object> {
                    {"schema", "rocell.camera_bench_control_restore.v1"},
                    {"device_name", expectedName}, {"device_path", expectedDevicePath},
                    {"changes", changes}, {"control_set_calls", 2}, {"streams_started", 0},
                    {"arm_access", false}, {"camera_only", true},
                    {"meaning", "Restore prior automatic modes after rejected manual-control trial."}
                };
            } finally {
                Release(filter);
                foreach (var item in matches) Release(item);
                Release(enumeration); Release(system);
            }
        }
    }
}
