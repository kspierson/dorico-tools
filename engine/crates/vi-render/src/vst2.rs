//! Minimal VST 2.4 host side: load a plug-in DLL, talk to it through its dispatcher, process
//! audio. The ABI (struct layouts, opcode numbers) follows the public re-implementations of the
//! VST2 interface (VeSTige, rust-vst); no Steinberg SDK code is used.
//!
//! Single-threaded on purpose: VST2 plug-ins expect dispatcher calls from one thread.

use std::ffi::{c_char, c_void, CStr};
use std::ptr;
use std::sync::Mutex;

use anyhow::{anyhow, bail, Result};

pub type Dispatcher = unsafe extern "C" fn(*mut AEffect, i32, i32, isize, *mut c_void, f32) -> isize;
type Process = unsafe extern "C" fn(*mut AEffect, *const *const f32, *mut *mut f32, i32);
type SetParameter = unsafe extern "C" fn(*mut AEffect, i32, f32);
type GetParameter = unsafe extern "C" fn(*mut AEffect, i32) -> f32;
type HostCallback = unsafe extern "C" fn(*mut AEffect, i32, i32, isize, *mut c_void, f32) -> isize;
type PluginMain = unsafe extern "C" fn(HostCallback) -> *mut AEffect;

#[repr(C)]
pub struct AEffect {
    pub magic: i32,
    pub dispatcher: Dispatcher,
    _process: Option<Process>,
    pub set_parameter: SetParameter,
    pub get_parameter: GetParameter,
    pub num_programs: i32,
    pub num_params: i32,
    pub num_inputs: i32,
    pub num_outputs: i32,
    pub flags: i32,
    _reserved1: isize,
    _reserved2: isize,
    pub initial_delay: i32,
    _real_qualities: i32,
    _off_qualities: i32,
    _io_ratio: f32,
    _object: *mut c_void,
    _user: *mut c_void,
    pub unique_id: i32,
    pub version: i32,
    pub process_replacing: Option<Process>,
    _process_double_replacing: Option<*const c_void>,
    _future: [u8; 56],
}

// effect opcodes
const EFF_OPEN: i32 = 0;
const EFF_CLOSE: i32 = 1;
const EFF_GET_PROGRAM_NAME: i32 = 5;
const EFF_GET_PARAM_LABEL: i32 = 6;
const EFF_GET_PARAM_DISPLAY: i32 = 7;
const EFF_GET_PARAM_NAME: i32 = 8;
const EFF_SET_SAMPLE_RATE: i32 = 10;
const EFF_SET_BLOCK_SIZE: i32 = 11;
const EFF_MAINS_CHANGED: i32 = 12;
const EFF_IDLE: i32 = 53;
const EFF_EDIT_OPEN: i32 = 14;
const EFF_EDIT_CLOSE: i32 = 15;
const EFF_EDIT_IDLE: i32 = 19;
const EFF_GET_CHUNK: i32 = 23;
const EFF_SET_CHUNK: i32 = 24;
const EFF_PROCESS_EVENTS: i32 = 25;
const EFF_GET_EFFECT_NAME: i32 = 45;
const EFF_GET_VENDOR_STRING: i32 = 47;
const EFF_GET_PRODUCT_STRING: i32 = 48;
const EFF_GET_VENDOR_VERSION: i32 = 49;
const EFF_START_PROCESS: i32 = 71;
const EFF_STOP_PROCESS: i32 = 72;

const FLAG_PROGRAM_CHUNKS: i32 = 1 << 5;
const MAGIC: i32 = i32::from_be_bytes(*b"VstP");

// host (audioMaster) opcodes
const AM_VERSION: i32 = 1;
const AM_CURRENT_ID: i32 = 2;
const AM_GET_TIME: i32 = 7;
const AM_GET_SAMPLE_RATE: i32 = 16;
const AM_GET_BLOCK_SIZE: i32 = 17;
const AM_GET_CURRENT_PROCESS_LEVEL: i32 = 23;
const AM_GET_AUTOMATION_STATE: i32 = 24;
const AM_GET_VENDOR_STRING: i32 = 32;
const AM_GET_PRODUCT_STRING: i32 = 33;
const AM_GET_VENDOR_VERSION: i32 = 34;
const AM_CAN_DO: i32 = 37;
const AM_GET_LANGUAGE: i32 = 38;

#[repr(C)]
#[derive(Default, Clone, Copy)]
struct TimeInfo {
    sample_pos: f64,
    sample_rate: f64,
    nano_seconds: f64,
    ppq_pos: f64,
    tempo: f64,
    bar_start_pos: f64,
    cycle_start_pos: f64,
    cycle_end_pos: f64,
    time_sig_numerator: i32,
    time_sig_denominator: i32,
    smpte_offset: i32,
    smpte_frame_rate: i32,
    samples_to_next_clock: i32,
    flags: i32,
}

/// Transport the host reports to the plug-in (one plug-in per process, so a global is fine).
static TIME: Mutex<TimeInfo> = Mutex::new(TimeInfo {
    sample_pos: 0.0, sample_rate: 48000.0, nano_seconds: 0.0, ppq_pos: 0.0, tempo: 120.0,
    bar_start_pos: 0.0, cycle_start_pos: 0.0, cycle_end_pos: 0.0, time_sig_numerator: 4,
    time_sig_denominator: 4, smpte_offset: 0, smpte_frame_rate: 0, samples_to_next_clock: 0, flags: 0,
});
static mut TIME_OUT: TimeInfo = TimeInfo {
    sample_pos: 0.0, sample_rate: 48000.0, nano_seconds: 0.0, ppq_pos: 0.0, tempo: 120.0,
    bar_start_pos: 0.0, cycle_start_pos: 0.0, cycle_end_pos: 0.0, time_sig_numerator: 4,
    time_sig_denominator: 4, smpte_offset: 0, smpte_frame_rate: 0, samples_to_next_clock: 0, flags: 0,
};
static BLOCK: Mutex<i32> = Mutex::new(256);
/// What the host reports as its process level: 2 = realtime, 4 = offline.
pub static PROCESS_LEVEL: Mutex<isize> = Mutex::new(4);

unsafe extern "C" fn host_callback(_e: *mut AEffect, opcode: i32, _index: i32, _value: isize,
                                   ptr: *mut c_void, _opt: f32) -> isize {
    unsafe fn put(ptr: *mut c_void, s: &str) -> isize {
        if !ptr.is_null() {
            let b = s.as_bytes();
            unsafe {
                ptr::copy_nonoverlapping(b.as_ptr(), ptr as *mut u8, b.len());
                *(ptr as *mut u8).add(b.len()) = 0;
            }
        }
        1
    }
    if std::env::var_os("VI_RENDER_DEBUG").is_some() && opcode != AM_GET_TIME {
        let extra = if opcode == AM_CAN_DO && !ptr.is_null() {
            unsafe { CStr::from_ptr(ptr as *const c_char) }.to_string_lossy().to_string()
        } else {
            String::new()
        };
        eprintln!("host callback: opcode {opcode} index {_index} value {_value} {extra}");
    }
    match opcode {
        AM_VERSION => 2400,
        AM_CURRENT_ID => 0,
        AM_GET_TIME => {
            let t = *TIME.lock().unwrap();
            // tempo valid | ppq valid | transport playing | time sig valid
            unsafe {
                TIME_OUT = t;
                TIME_OUT.flags = (1 << 10) | (1 << 9) | 2 | (1 << 13);
                (&raw mut TIME_OUT) as isize
            }
        }
        AM_GET_SAMPLE_RATE => TIME.lock().unwrap().sample_rate as isize,
        AM_GET_BLOCK_SIZE => *BLOCK.lock().unwrap() as isize,
        AM_GET_CURRENT_PROCESS_LEVEL => *PROCESS_LEVEL.lock().unwrap(),
        AM_GET_AUTOMATION_STATE => 1,      // off
        AM_GET_VENDOR_STRING => unsafe { put(ptr, "dorico-test") },
        AM_GET_PRODUCT_STRING => unsafe { put(ptr, "vi-render") },
        AM_GET_VENDOR_VERSION => 1,
        AM_GET_LANGUAGE => 1,
        AM_CAN_DO => {
            if ptr.is_null() {
                return 0;
            }
            let s = unsafe { CStr::from_ptr(ptr as *const c_char) }.to_string_lossy();
            match s.as_ref() {
                "sendVstEvents" | "sendVstMidiEvent" | "sendVstTimeInfo" | "receiveVstEvents"
                | "receiveVstMidiEvent" | "supportShell" | "offline" => 1,
                _ => 0,
            }
        }
        _ => 0,
    }
}

#[repr(C)]
#[derive(Clone, Copy)]
struct MidiEvent {
    kind: i32,       // 1 = MIDI
    byte_size: i32,  // 32
    delta_frames: i32,
    flags: i32,      // 1 = realtime
    note_length: i32,
    note_offset: i32,
    data: [u8; 4],
    detune: i8,
    note_off_velocity: u8,
    _r1: u8,
    _r2: u8,
}

/// Run the Windows message loop for `ms` milliseconds (and give the plug-in idle time).
/// JUCE plug-ins (SWAM) finish loading and react to state changes through posted messages and
/// timers; without a message loop they stay silent.
#[cfg(windows)]
pub fn pump(ms: u64) {
    #[repr(C)]
    struct Msg {
        hwnd: isize,
        message: u32,
        wparam: usize,
        lparam: isize,
        time: u32,
        pt: [i32; 2],
        private: u32,
    }
    #[link(name = "user32")]
    unsafe extern "system" {
        fn PeekMessageW(msg: *mut Msg, hwnd: isize, min: u32, max: u32, remove: u32) -> i32;
        fn TranslateMessage(msg: *const Msg) -> i32;
        fn DispatchMessageW(msg: *const Msg) -> isize;
    }
    let end = std::time::Instant::now() + std::time::Duration::from_millis(ms);
    loop {
        let mut m = Msg { hwnd: 0, message: 0, wparam: 0, lparam: 0, time: 0, pt: [0, 0], private: 0 };
        while unsafe { PeekMessageW(&mut m, 0, 0, 0, 1) } != 0 {
            unsafe {
                TranslateMessage(&m);
                DispatchMessageW(&m);
            }
        }
        if std::time::Instant::now() >= end {
            break;
        }
        std::thread::sleep(std::time::Duration::from_millis(2));
    }
}

#[cfg(not(windows))]
pub fn pump(ms: u64) {
    std::thread::sleep(std::time::Duration::from_millis(ms));
}

/// A plain top-level window to host a plug-in editor (hidden unless `show`).
#[cfg(windows)]
pub fn make_window(show: bool) -> isize {
    #[link(name = "user32")]
    unsafe extern "system" {
        fn CreateWindowExW(ex: u32, class: *const u16, name: *const u16, style: u32, x: i32, y: i32, w: i32,
                           h: i32, parent: isize, menu: isize, inst: isize, param: *mut c_void) -> isize;
        fn ShowWindow(hwnd: isize, cmd: i32) -> i32;
    }
    let w = |s: &str| s.encode_utf16().chain(std::iter::once(0)).collect::<Vec<u16>>();
    let (class, name) = (w("STATIC"), w("vi-render"));
    // WS_OVERLAPPEDWINDOW
    let hwnd = unsafe { CreateWindowExW(0, class.as_ptr(), name.as_ptr(), 0x00CF0000, 100, 100, 900, 700, 0, 0, 0,
                                        ptr::null_mut()) };
    if show && hwnd != 0 {
        unsafe { ShowWindow(hwnd, 5) };
    }
    hwnd
}

/// Save what a window shows as a 32-bit BMP (for checking a plug-in's own status messages).
#[cfg(windows)]
pub fn capture(hwnd: isize, path: &str) -> Result<()> {
    #[repr(C)]
    struct BitmapInfoHeader {
        size: u32, width: i32, height: i32, planes: u16, bit_count: u16, compression: u32, size_image: u32,
        xppm: i32, yppm: i32, clr_used: u32, clr_important: u32,
    }
    #[link(name = "user32")]
    unsafe extern "system" {
        fn GetWindowRect(hwnd: isize, r: *mut [i32; 4]) -> i32;
        fn GetDC(hwnd: isize) -> isize;
        fn ReleaseDC(hwnd: isize, dc: isize) -> i32;
        fn PrintWindow(hwnd: isize, dc: isize, flags: u32) -> i32;
    }
    #[link(name = "gdi32")]
    unsafe extern "system" {
        fn CreateCompatibleDC(dc: isize) -> isize;
        fn CreateCompatibleBitmap(dc: isize, w: i32, h: i32) -> isize;
        fn SelectObject(dc: isize, obj: isize) -> isize;
        fn GetDIBits(dc: isize, bmp: isize, start: u32, lines: u32, bits: *mut c_void, bmi: *mut BitmapInfoHeader, usage: u32) -> i32;
        fn DeleteObject(obj: isize) -> i32;
        fn DeleteDC(dc: isize) -> i32;
    }
    let mut r = [0i32; 4];
    unsafe { GetWindowRect(hwnd, &mut r) };
    let (w, h) = (r[2] - r[0], r[3] - r[1]);
    if w <= 0 || h <= 0 {
        bail!("window has no size");
    }
    let mut px = vec![0u8; (w * h * 4) as usize];
    unsafe {
        let wdc = GetDC(hwnd);
        let mdc = CreateCompatibleDC(wdc);
        let bmp = CreateCompatibleBitmap(wdc, w, h);
        let old = SelectObject(mdc, bmp);
        PrintWindow(hwnd, mdc, 2);
        let mut bi = BitmapInfoHeader { size: 40, width: w, height: h, planes: 1, bit_count: 32, compression: 0,
                                        size_image: 0, xppm: 0, yppm: 0, clr_used: 0, clr_important: 0 };
        GetDIBits(mdc, bmp, 0, h as u32, px.as_mut_ptr() as *mut c_void, &mut bi, 0);
        SelectObject(mdc, old);
        DeleteObject(bmp);
        DeleteDC(mdc);
        ReleaseDC(hwnd, wdc);
    }
    let mut out = Vec::with_capacity(54 + px.len());
    out.extend_from_slice(b"BM");
    out.extend_from_slice(&(54 + px.len() as u32).to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&54u32.to_le_bytes());
    for v in [40u32, w as u32, h as u32] {
        out.extend_from_slice(&v.to_le_bytes());
    }
    out.extend_from_slice(&1u16.to_le_bytes());
    out.extend_from_slice(&32u16.to_le_bytes());
    out.extend_from_slice(&[0u8; 24]);
    out.extend_from_slice(&px);
    std::fs::write(path, out)?;
    Ok(())
}

#[cfg(not(windows))]
pub fn capture(_hwnd: isize, _path: &str) -> Result<()> {
    bail!("capture needs Windows")
}

#[cfg(not(windows))]
pub fn make_window(_show: bool) -> isize {
    0
}

pub struct Plugin {
    _lib: libloading::Library,
    eff: *mut AEffect,
    open: bool,
}

pub struct ParamInfo {
    pub index: i32,
    pub name: String,
    pub label: String,
    pub display: String,
    pub value: f32,
}

fn cstr(buf: &[u8]) -> String {
    let end = buf.iter().position(|&b| b == 0).unwrap_or(buf.len());
    String::from_utf8_lossy(&buf[..end]).trim().to_string()
}

impl Plugin {
    pub fn load(path: &str, sample_rate: f64, block: usize) -> Result<Plugin> {
        let lib = unsafe { libloading::Library::new(path) }.map_err(|e| anyhow!("loading {path}: {e}"))?;
        let main: PluginMain = unsafe {
            match lib.get::<PluginMain>(b"VSTPluginMain\0") {
                Ok(f) => *f,
                Err(_) => *lib.get::<PluginMain>(b"main\0").map_err(|e| anyhow!("no VST2 entry point: {e}"))?,
            }
        };
        {
            let mut t = TIME.lock().unwrap();
            t.sample_rate = sample_rate;
            *BLOCK.lock().unwrap() = block as i32;
        }
        let eff = unsafe { main(host_callback) };
        if eff.is_null() {
            bail!("{path}: plug-in returned no instance");
        }
        if unsafe { (*eff).magic } != MAGIC {
            bail!("{path}: not a VST2 plug-in (bad magic)");
        }
        let mut p = Plugin { _lib: lib, eff, open: false };
        p.dispatch(EFF_OPEN, 0, 0, ptr::null_mut(), 0.0);
        p.open = true;
        p.dispatch(EFF_SET_SAMPLE_RATE, 0, 0, ptr::null_mut(), sample_rate as f32);
        p.dispatch(EFF_SET_BLOCK_SIZE, 0, block as isize, ptr::null_mut(), 0.0);
        p.idle(300);
        Ok(p)
    }

    fn dispatch(&mut self, op: i32, index: i32, value: isize, ptr: *mut c_void, opt: f32) -> isize {
        unsafe { ((*self.eff).dispatcher)(self.eff, op, index, value, ptr, opt) }
    }

    fn string(&mut self, op: i32, index: i32) -> String {
        let mut buf = [0u8; 512];
        self.dispatch(op, index, 0, buf.as_mut_ptr() as *mut c_void, 0.0);
        cstr(&buf)
    }

    pub fn info(&mut self) -> serde_json::Value {
        let e = unsafe { &*self.eff };
        let (np, ni, no, flags, id, ver, delay) =
            (e.num_params, e.num_inputs, e.num_outputs, e.flags, e.unique_id, e.version, e.initial_delay);
        serde_json::json!({
            "effect": self.string(EFF_GET_EFFECT_NAME, 0),
            "vendor": self.string(EFF_GET_VENDOR_STRING, 0),
            "product": self.string(EFF_GET_PRODUCT_STRING, 0),
            "vendor_version": self.dispatch(EFF_GET_VENDOR_VERSION, 0, 0, ptr::null_mut(), 0.0),
            "program": self.string(EFF_GET_PROGRAM_NAME, 0),
            "unique_id": String::from_utf8_lossy(&id.to_be_bytes()).to_string(),
            "version": ver, "params": np, "inputs": ni, "outputs": no,
            "program_chunks": flags & FLAG_PROGRAM_CHUNKS != 0,
            "initial_delay_samples": delay,
        })
    }

    pub fn num_params(&self) -> i32 {
        unsafe { (*self.eff).num_params }
    }

    pub fn params(&mut self) -> Vec<ParamInfo> {
        (0..self.num_params())
            .map(|i| ParamInfo {
                index: i,
                name: self.string(EFF_GET_PARAM_NAME, i),
                label: self.string(EFF_GET_PARAM_LABEL, i),
                display: self.string(EFF_GET_PARAM_DISPLAY, i),
                value: self.get_param(i),
            })
            .collect()
    }

    pub fn get_param(&mut self, i: i32) -> f32 {
        unsafe { ((*self.eff).get_parameter)(self.eff, i) }
    }

    pub fn set_param(&mut self, i: i32, v: f32) {
        unsafe { ((*self.eff).set_parameter)(self.eff, i, v) }
    }

    pub fn param_display(&mut self, i: i32) -> String {
        self.string(EFF_GET_PARAM_DISPLAY, i)
    }

    /// The plug-in's state blob (program chunk if `program`, else bank chunk).
    pub fn get_chunk(&mut self, program: bool) -> Vec<u8> {
        let mut data: *mut c_void = ptr::null_mut();
        let n = self.dispatch(EFF_GET_CHUNK, program as i32, 0, (&mut data) as *mut _ as *mut c_void, 0.0);
        if n <= 0 || data.is_null() {
            return Vec::new();
        }
        unsafe { std::slice::from_raw_parts(data as *const u8, n as usize) }.to_vec()
    }

    pub fn set_chunk(&mut self, program: bool, data: &[u8]) -> isize {
        let mut owned = data.to_vec();
        self.dispatch(EFF_SET_CHUNK, program as i32, owned.len() as isize, owned.as_mut_ptr() as *mut c_void, 0.0)
    }

    /// Open the plug-in's editor in `hwnd` for `ms` milliseconds (running the message loop), then close it.
    pub fn open_editor(&mut self, hwnd: isize, ms: u64, shot: Option<&str>) -> isize {
        let r = self.dispatch(EFF_EDIT_OPEN, 0, 0, hwnd as *mut c_void, 0.0);
        let end = std::time::Instant::now() + std::time::Duration::from_millis(ms);
        while std::time::Instant::now() < end {
            self.dispatch(EFF_EDIT_IDLE, 0, 0, ptr::null_mut(), 0.0);
            pump(20);
        }
        if let Some(path) = shot {
            if let Err(e) = capture(hwnd, path) {
                eprintln!("screenshot failed: {e}");
            }
        }
        self.dispatch(EFF_EDIT_CLOSE, 0, 0, ptr::null_mut(), 0.0);
        r
    }

    /// Message loop + effIdle for `ms` milliseconds.
    pub fn idle(&mut self, ms: u64) {
        self.dispatch(EFF_IDLE, 0, 0, ptr::null_mut(), 0.0);
        pump(ms);
    }

    pub fn resume(&mut self) {
        self.dispatch(EFF_MAINS_CHANGED, 0, 1, ptr::null_mut(), 0.0);
        self.dispatch(EFF_START_PROCESS, 0, 0, ptr::null_mut(), 0.0);
    }

    pub fn suspend(&mut self) {
        self.dispatch(EFF_STOP_PROCESS, 0, 0, ptr::null_mut(), 0.0);
        self.dispatch(EFF_MAINS_CHANGED, 0, 0, ptr::null_mut(), 0.0);
    }

    /// Send MIDI events for the next block. `events`: (offset in block, bytes).
    pub fn send_midi(&mut self, events: &[(usize, [u8; 3])]) {
        if events.is_empty() {
            return;
        }
        let midi: Vec<MidiEvent> = events
            .iter()
            .map(|(off, b)| MidiEvent {
                kind: 1, byte_size: 32, delta_frames: *off as i32, flags: 1, note_length: 0, note_offset: 0,
                data: [b[0], b[1], b[2], 0], detune: 0, note_off_velocity: 0, _r1: 0, _r2: 0,
            })
            .collect();
        // VstEvents { i32 num; isize reserved; *VstEvent events[num] }
        #[repr(C)]
        struct Header {
            num: i32,
            reserved: isize,
        }
        let mut buf: Vec<u8> = vec![0; size_of::<Header>() + midi.len().max(2) * size_of::<*const MidiEvent>()];
        unsafe {
            let h = buf.as_mut_ptr() as *mut Header;
            (*h).num = midi.len() as i32;
            (*h).reserved = 0;
            let ptrs = buf.as_mut_ptr().add(size_of::<Header>()) as *mut *const MidiEvent;
            for (i, m) in midi.iter().enumerate() {
                *ptrs.add(i) = m as *const MidiEvent;
            }
        }
        self.dispatch(EFF_PROCESS_EVENTS, 0, 0, buf.as_mut_ptr() as *mut c_void, 0.0);
    }

    /// Process one block; `out` has one Vec per output channel, each `n` long.
    pub fn process(&mut self, inputs: &[Vec<f32>], out: &mut [Vec<f32>], n: usize, sample_pos: f64) -> Result<()> {
        {
            let mut t = TIME.lock().unwrap();
            t.sample_pos = sample_pos;
            t.ppq_pos = sample_pos / t.sample_rate * t.tempo / 60.0;
        }
        let f = unsafe { (*self.eff).process_replacing }.ok_or_else(|| anyhow!("plug-in has no processReplacing"))?;
        let ins: Vec<*const f32> = inputs.iter().map(|v| v.as_ptr()).collect();
        let mut outs: Vec<*mut f32> = out.iter_mut().map(|v| v.as_mut_ptr()).collect();
        unsafe { f(self.eff, ins.as_ptr(), outs.as_mut_ptr(), n as i32) };
        Ok(())
    }

    pub fn flags(&self) -> i32 {
        unsafe { (*self.eff).flags }
    }

    pub fn io(&self) -> (usize, usize) {
        unsafe { ((*self.eff).num_inputs.max(0) as usize, (*self.eff).num_outputs.max(0) as usize) }
    }
}

impl Drop for Plugin {
    fn drop(&mut self) {
        if self.open {
            self.dispatch(EFF_CLOSE, 0, 0, ptr::null_mut(), 0.0);
        }
    }
}
