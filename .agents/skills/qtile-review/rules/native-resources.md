# Native code and resource management

Applies to the C code in `libqtile/backend/wayland/qw/` and to Python code that
calls into it through cffi.

## 23. Every acquisition has a matching release

For each resource the change acquires, find the matching release and confirm
it runs on every path.

**What counts as a resource:**

- **Memory:** `malloc`/`calloc`/`realloc`, `strdup`, `asprintf`, and library
  calls that transfer ownership to the caller (for example
  `pango_parse_markup`, `g_markup_escape_text`).
- **File descriptors:** `open`, `socket`, `pipe`, `dup`, `eventfd`,
  `memfd_create`, and fds received over a Wayland or Unix socket. New fds
  should be opened with `O_CLOEXEC`/`SOCK_CLOEXEC`.
- **Wayland and wlroots objects:**
  - objects created with `*_create` or `wl_resource_create`, which need their
    `*_destroy` or `wl_resource_destroy`
  - buffer locks (`wlr_buffer_lock` needs a matching `wlr_buffer_unlock`)
  - initialised structs that need a `*_finish`/`*_fini`, such as
    `pixman_region32_fini`
  - event sources added to the event loop, which need `wl_event_source_remove`
- **Signal listeners:** every `wl_signal_add` needs a
  `wl_list_remove(&listener.link)` in the destroy handler. A listener that is
  never removed is a leak and a use-after-free waiting to happen.
- **Library handles:** xkb keymaps and states (`xkb_*_unref`), cairo surfaces,
  libinput, and udev references.

**What to check:**

- **Error paths.** Trace every early `return` and `goto` after an acquisition.
  Resources acquired before a failure point must be released, ideally through a
  single `goto cleanup` chain that releases in reverse order. Partial
  initialisation is where most leaks hide.
- **Ownership is clear.** When a pointer or fd is passed to another function or
  to Python, a comment or the function name should say who frees it. Flag any
  transfer where ownership is ambiguous.
- **Destroy handlers are complete.** When a struct is destroyed, every resource
  it holds is released: child objects, listeners, timers, buffers and fds.
- **Objects that outlive their parent.** If an object can outlive the object it
  points to (a surface outliving its output, for example), it must listen for
  the parent's destroy signal and clear its pointer.
- **No double frees or use-after-free.** After a release, the pointer or fd
  should be set to `NULL`/`-1`, or the release must clearly be the last use.

**Python side (cffi):**

- Memory from `ffi.new` lives only as long as the Python object that holds it.
  Flag cases where C code stores such a pointer beyond that object's lifetime.
- `ffi.new_handle` results must stay referenced (e.g. as `self._userdata`) for
  as long as C can call back with them, and C must stop using the handle when
  the Python object is finalised.
- C-allocated memory or objects returned to Python must be freed explicitly,
  either with `ffi.gc(ptr, destructor)` or a matching release call in
  `finalize`/`destroy`.
- Python fds and sockets must be closed with a context manager or in
  `finalize`.

**Per-acquisition report table:**

| Resource | Acquired at (file:line) | Released at (file:line) | Paths that skip the release |
|---|---|---|---|

CI runs the test suite under AddressSanitizer (`Dockerfile.asan`); new C code
paths should be covered by tests so ASan can catch leaks this review misses.
