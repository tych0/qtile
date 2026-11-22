# Concurrency and the event loop

qtile runs on a single asyncio event loop. Anything that blocks it freezes the
whole window manager, and anything touching qtile state from another thread can
corrupt it.

## 1. No new threads, including ones that dependencies create

**Direct threads.** Flag `threading.Thread`, `_thread`, `concurrent.futures`
executors, `multiprocessing`, and direct calls to `loop.run_in_executor` in the
diff. Allowed:

- widgets subclassing `libqtile.widget.base.BackgroundPoll`. Prefer
  `async def apoll()`; a synchronous `poll()` is run in an executor by the base
  class and is acceptable when no async API exists.
- `qtile.run_in_executor(...)` for a short, one-off blocking call, when the PR
  explains why no async alternative exists.

Anything else needs a stated reason in the PR or commit message.

**New dependencies.** For every library the PR adds (check imports,
`pyproject.toml` extras, and the widget's documented requirements), work out
whether it creates threads or blocks:

- Read the library's source (the installed package or its upstream repository)
  and search for `threading`, `_thread`, `ThreadPoolExecutor`,
  `concurrent.futures`, `run_in_executor` and `multiprocessing`. For C
  extensions, search the bundled sources for `pthread_create` / `std::thread`.
- Check the API calls the PR actually uses, not just whether the library
  contains threading somewhere. Common patterns that start threads:
  - "start/observer/listener" calls, such as paho-mqtt's `loop_start()`,
    pyudev's `MonitorObserver`, watchdog's `Observer` and pynput listeners
  - libraries that run their own GLib or other main loop
  - audio and hardware libraries whose callbacks fire on a native thread
- Check the transitive dependencies the PR pulls in, for the code path it uses.
- Check for blocking calls. Synchronous network, file or IPC calls on the event
  loop are a problem even when the library creates no threads.

What to require:

- If the library has an asyncio interface or a non-threaded mode (for example,
  a file descriptor qtile can add to its event loop), the PR must use it.
- If threads can't be avoided, the PR must explain why. Every callback from the
  library's thread must reach qtile state only through
  `qtile.call_soon_threadsafe`. Its threads and observers must be stopped in
  `finalize()`, and must not keep qtile from exiting (daemon threads, or joined
  on shutdown).
- If you can't tell whether a dependency starts threads, flag it as a question
  for the author rather than passing it.

Per-dependency report table:

| Library | APIs used | Creates threads? (yes/no/unknown + evidence: file:line or docs link) | Blocks? | What the PR does about it |
|---|---|---|---|---|

## 2. Don't block the event loop

Flag `subprocess.run`, `subprocess.check_output`, `time.sleep`, synchronous
network or file I/O, and slow D-Bus calls in hooks, commands, layouts, and
`InLoopPollText` widgets (which run in the loop). Suggest the asyncio
equivalent (`asyncio.create_subprocess_exec`, `asyncio.sleep`, the async D-Bus
helpers), or `BackgroundPoll`.

## 3. Thread safety

Any callback that can run off the event loop thread (executor work, library
callbacks, signal handlers) must hand work back with
`qtile.call_soon_threadsafe` and must not touch qtile objects directly.

## 4. Clean up timers and tasks

Timers (`timeout_add`), futures, tasks and hook subscriptions created in
`__init__`/`_configure` must be cancelled or unsubscribed in `finalize()`.
Tasks created with `create_task` must be kept referenced, so they aren't
garbage-collected silently, and their exceptions must not be lost.
