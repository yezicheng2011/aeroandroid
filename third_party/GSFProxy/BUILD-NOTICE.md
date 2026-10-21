This source snapshot is from the official microG GsfProxy repository commit
`ff1b9aa3e235904009f1d87113391abb51808af1`:
https://github.com/microg/GsfProxy/tree/ff1b9aa3e235904009f1d87113391abb51808af1

Code is Apache-2.0. Documentation/artwork licensing is recorded in `.reuse`,
README and LICENSES (CC-BY-SA-4.0 and CC0-1.0 where applicable). These license
files are included with the source and should be retained in distribution.

`../../microg-spoof/build-microg-tools.sh` provides the offline build. The
original Java source and resources are unchanged. The script generates a
manifest with package `com.google.android.gsf`, min/target SDK 24 and labels
the resulting APK `0.1.0-source-ff1b9aa3`. It signs with the private subsystem
development key rather than claiming an official microG release signature.
The target SDK matches the current upstream build setting and does not use
an Android low-target-SDK installation bypass.

GSFProxy forwards legacy C2DM registration requests to microG Services. It
is not Google's proprietary Google Services Framework or a standalone GMS
replacement. Its functioning still requires Guest runtime validation.
