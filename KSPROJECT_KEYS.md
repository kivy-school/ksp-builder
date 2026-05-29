# ksproject Keys Summary & ksp-builder Comparison

This document lists all configuration keys recognized by **ksproject** under `[tool.kivy-school]` in `pyproject.toml`, and compares them to what **ksp-builder** currently reads/uses.

---

## `[tool.kivy-school]`

| Key | Type | ksproject | ksp-builder |
|-----|------|-----------|-------------|
| `app_name` | `str` | ✅ Used | ❌ Not read |

---

## `[tool.kivy-school.android]`

| Key | Type | ksproject | ksp-builder |
|-----|------|-----------|-------------|
| `package_name` | `str` | ✅ Required | ✅ Used (falls back to `[project].name`) |
| `archs` | `list[str]` | ✅ Used (arm64-v8a, x86_64) | ❌ Not read |
| `api` | `int` | ✅ Used (target API level) | ❌ Not read |
| `min_api` | `int` | ✅ Used (minimum API level) | ❌ Not read |
| `sdk` | `str` | ✅ Used (SDK version string) | ❌ Not read |
| `ndk` | `str` | ✅ Used (NDK version) | ❌ Not read |
| `ndk_api` | `int` | ✅ Used (NDK API level) | ❌ Not read |
| `sdk_path` | `str` (path) | ✅ Used (override SDK location) | ❌ Not read |
| `ndk_path` | `str` (path) | ✅ Used (override NDK location) | ❌ Not read |
| `java_path` | `str` (path) | ✅ Used (override JDK location) | ❌ Not read |
| `global_tools` | `bool` | ✅ Used (use shared tool installs) | ❌ Not read |
| `global_tools_path` | `str` (path) | ✅ Used (override ~/.kivyschool for global) | ❌ Not read |
| `icon` | `str` (path) | ✅ Used (app icon asset) | ❌ Not read |
| `presplash` | `str` (path) | ✅ Used (splash screen image) | ❌ Not read |
| `presplash_color` | `str` | ✅ Used (splash background color) | ❌ Not read |
| `presplash_lottie` | `str` (path) | ✅ Used (Lottie splash animation) | ❌ Not read |
| `permissions` | `list[str]` | ✅ Used (Android manifest permissions) | ✅ Used |
| `meta_data` | `dict[str, str]` | ✅ Used (AndroidManifest meta-data) | ✅ Used |
| `gradle_dependencies` | `list[str]` | ✅ Used (Maven deps in build.gradle.kts) | ✅ Used |
| `services` | `list[ServiceData]` | ✅ Used (Android background services) | ❌ Not read |

### Service keys (`[[tool.kivy-school.android.services]]`)

| Key | Type | ksproject | ksp-builder |
|-----|------|-----------|-------------|
| `name` | `str` | ✅ Required | ❌ Not read |
| `entrypoint` | `str` | ✅ Used (Python module path) | ❌ Not read |
| `foreground` | `bool` | ✅ Used (default: false) | ❌ Not read |
| `foreground_service_type` | `str` | ✅ Used (e.g. "location\|dataSync") | ❌ Not read |
| `start_type` | `str` | ✅ Documented (START_STICKY etc.) | ❌ Not read |
| `notification_title` | `str` | ✅ Documented | ❌ Not read |
| `notification_text` | `str` | ✅ Documented | ❌ Not read |
| `notification_icon` | `str` | ✅ Documented | ❌ Not read |

> **Note:** `start_type`, `notification_title`, `notification_text`, and `notification_icon` appear in the ksproject README examples but are not yet parsed in `ServiceData.__init__` in the source code.

---

## `[tool.kivy-school.ios]`

| Key | Type | ksproject | ksp-builder |
|-----|------|-----------|-------------|
| `bundle_id` | `str` | ✅ Required | ❌ Not read |
| `info_plist` | `dict` | ✅ Used | ❌ Not read |
| `entitlements` | `dict` | ✅ Used | ❌ Not read |
| `permissions` | `list[str]` | ✅ Used | ❌ Not read |
| `frameworks` | `list[str]` | ✅ Used | ❌ Not read |
| `site_frameworks` | `list[str]` | ✅ Used | ❌ Not read |
| `developer_team` | `str` | ✅ Used (Apple Team ID) | ❌ Not read |

---

## `[tool.kivy-school.macos]`

| Key | Type | ksproject | ksp-builder |
|-----|------|-----------|-------------|
| `bundle_id` | `str` | ✅ Required | ❌ Not read |
| `info_plist` | `dict` | ✅ Used | ❌ Not read |
| `entitlements` | `dict` | ✅ Used | ❌ Not read |
| `developer_team` | `str` | ✅ Used (Apple Team ID) | ❌ Not read |

---

## Summary

**ksp-builder** currently only reads from `[tool.kivy-school.android]` and uses **4 keys**:

1. `package_name` — identifies the package for the `.gradle/<name>.json` artifact
2. `gradle_dependencies` — Maven dependencies to inject
3. `permissions` — Android permissions to inject
4. `meta_data` — AndroidManifest `<meta-data>` entries to inject

These are the keys that get serialized into the `.gradle/<package_name>.json` file which ksproject later collects and merges from all installed site-packages at build time.

**ksproject** recognizes **30+ keys** across android, ios, and macos platform sections, plus the top-level `app_name`.
