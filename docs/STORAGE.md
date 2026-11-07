# Shared storage

Shared Mac folders appear as **Mac · <folder name>** in Android's system file picker. Android applications
that use the Storage Access Framework can open, edit, create and save files directly in the selected folder.
Finder and Android access the same host files; the bridge does not maintain synchronized copies or stage whole files.

## Use

1. Open **Files → Shared Mac folders** in the Mac manager.
2. Choose **Add folders**, select one or more folders, and choose read/write or read-only access.
3. Choose **Connect to Android**. The controller starts Android, installs the matching bridge and connects it locally.
4. In an Android app, use **Open**, **Save as** or **Choose folder**, then select a **Mac · …** location.
5. Use **Open in Finder** to access the same folder on the Mac. **Stop sharing** revokes that shared root without
   deleting its files or stopping Android.

Sharing is restored automatically whenever the subsystem starts, including launches from exported Mac apps.
Folders can be added or removed while Android is running; no reboot is required. Existing folders can be shared
again with a different access setting. The legacy Android `Download/MacBridge` import/export UI remains available
for applications that work only with local Android storage.

macOS may ask for access to protected locations such as Documents or Desktop. The bridge uses your normal Mac
user permissions; selecting a folder does not bypass macOS privacy controls or filesystem permissions.

## Scope and behavior

- Access is limited to folders explicitly selected in the manager. You can select a broad folder if needed;
  the system does not silently publish the entire Mac disk.
- Android's ordinary per-document and folder URI grants control which applications can use each selection.
- Read-only roots reject create, write, truncate, rename and delete, including operations through previously opened documents.
- Changes are visible on the next read or query. Android's picker may need refresh/reopen to display files created or
  renamed externally on the Mac; there is no background filesystem watcher.
- File names can contain Unicode and nested directories. Large directory listings are fetched in pages.
- Reads and writes are chunked and support seeking, append, truncate and flush. No whole-file copy is needed to open a file.
- Replacing or renaming a file in Finder while Android holds it open can invalidate that open document. File identity
  checks prevent an old Android descriptor from overwriting a replacement; reopen the file to continue.
- File and empty-directory deletion is supported. Nonempty directories are not recursively erased by the bridge.
- Multiple editors share the same bytes. There is no automatic conflict merge or cross-application file locking.
- Symbolic links and special files are not followed or exposed through shared roots.
- This is a document provider, not a POSIX filesystem mount. Apps that require raw `/sdcard` paths, Android private
  app directories or filesystem-specific operations do not automatically gain access to Mac folders.

## Local architecture

`backend/storage_service.py` is an original, Python-standard-library-only service bound to a random loopback port.
The controller establishes `adb reverse tcp:7901 tcp:<host port>` for the owned emulator and supplies a private
credential to the bridge through its DUMP-protected provider. The Android document provider connects only to
`127.0.0.1:7901`; its cleartext HTTP allowance is restricted to loopback. There is no LAN listener or cloud upload.

Each file operation authenticates and reloads the explicit share list. Directory descriptors and no-follow opens
keep paths below the chosen root. File identities are checked on opened descriptors before modifications. Error
names are translated between Darwin and Android rather than assuming their numeric errno values match.

`StorageManager.openProxyFileDescriptor` connects Android seekable file descriptors to bounded, direct host reads
and writes. The Mac service stops with Android, and an emulator identity watcher handles unexpected emulator exit.
Saved shared roots and files remain available for the next boot. Credentials and configuration live in the private
subsystem support directory and are never put in the repository.

## Validation

The unit suite exercises the real HTTP service and controller lifecycle, including authentication, directory
traversal and symlink refusal, read-only enforcement, revocation, random writes, atomic append, replacement-file
protection, pagination and restart. CI compiles both the native Mac UI and Java bridge against the pinned Android SDK.

Real Mac/Android acceptance still needs a SAF-compatible editor: open a Finder-created file, edit and save in
Android, verify the result in Finder, create a nested Unicode folder, test read-only mode, revoke a root while
open, stop/restart Android and test provider access after Quick Boot. This cannot be proved by host fixtures alone.
