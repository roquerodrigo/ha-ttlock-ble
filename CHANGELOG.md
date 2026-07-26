# Changelog

## [3.2.2](https://github.com/roquerodrigo/ha-ttlock-ble/compare/v3.2.1...v3.2.2) (2026-07-26)


### Bug Fixes

* **connection:** reduce reconnect cooldown to 5 minutes ([76967ba](https://github.com/roquerodrigo/ha-ttlock-ble/commit/76967baf75bb5bb3180cd79e68678c288b3ecb42))
* **init:** schedule first refresh via tracked config entry task ([411753e](https://github.com/roquerodrigo/ha-ttlock-ble/commit/411753e4506502fb970eb909aaa5a993c2254c5b))
* **manifest:** align ttlock-ble requirement with pyproject ([42fb0ee](https://github.com/roquerodrigo/ha-ttlock-ble/commit/42fb0eeac9b9dd3bc56a32786dcae6df1fd8653c))


### Performance Improvements

* reduce Home Assistant startup delay ([1926ebe](https://github.com/roquerodrigo/ha-ttlock-ble/commit/1926ebe6772ee91b6fed13b2dd1a2462046599b4))


### Documentation

* **CLAUDE:** update reconnect cooldown description to 5 minutes ([03c41d0](https://github.com/roquerodrigo/ha-ttlock-ble/commit/03c41d054ddf7f905499cb094612de87a8fbdf8e))
* update CLAUDE.md ([ed9ca22](https://github.com/roquerodrigo/ha-ttlock-ble/commit/ed9ca22f00bbb561d802a4cb6bc976a4ad03240e))

## [3.2.1](https://github.com/roquerodrigo/ha-ttlock-ble/compare/v3.2.0...v3.2.1) (2026-05-25)


### Documentation

* fix CI badge and drop license badge ([bff31f3](https://github.com/roquerodrigo/ha-ttlock-ble/commit/bff31f3566da79658db7675545307ee9931b3311))
* fix CI badge and drop license badge ([9cd5b30](https://github.com/roquerodrigo/ha-ttlock-ble/commit/9cd5b300c9cd0d1243bf3f2bfb98f1ec0cef8cf7))

## [3.2.0](https://github.com/roquerodrigo/ha-ttlock-ble/compare/v3.1.0...v3.2.0) (2026-05-18)


### Features

* **event:** use real datetime from SDK 0.1.5 for log timestamps ([b4971ac](https://github.com/roquerodrigo/ha-ttlock-ble/commit/b4971ac632c195e407a4ce4deff75bb5b7d813e7))

## [3.1.0](https://github.com/roquerodrigo/ha-ttlock-ble/compare/v3.0.1...v3.1.0) (2026-05-17)


### Features

* **event:** add operation log entity; remove push-event entity ([09138ff](https://github.com/roquerodrigo/ha-ttlock-ble/commit/09138ff93532c96e6afd18af36237e4d4fc6fbc7))
* fetch operation log records on each BLE connection ([d900838](https://github.com/roquerodrigo/ha-ttlock-ble/commit/d90083889beb1c3024e827ba654d15b219f00912))


### Bug Fixes

* **types:** align with SDK 0.1.4 LockState return type ([5938756](https://github.com/roquerodrigo/ha-ttlock-ble/commit/5938756dba846fa1cb7287cff583de23c918792f))

## [3.0.1](https://github.com/roquerodrigo/ha-ttlock-ble/compare/v3.0.0...v3.0.1) (2026-05-13)


### Bug Fixes

* cool down after any BLE drop instead of retrying 3 times ([cf26eb5](https://github.com/roquerodrigo/ha-ttlock-ble/commit/cf26eb5291e7d881f80b36c03abf88da4afccf7e))
* stretch BLE timings so polls don't fight the lock's idle-sleep ([8f02d92](https://github.com/roquerodrigo/ha-ttlock-ble/commit/8f02d92a4d09a71e803232f87e9308a57e193eaf))

## [3.0.0](https://github.com/roquerodrigo/ha-ttlock-ble/compare/v2.0.0...v3.0.0) (2026-05-13)


### ⚠ BREAKING CHANGES

* reverts the v2.0 on-demand BLE session model. Battery drain returns to the v1.x persistent-session profile in exchange for real-time state updates between polls.

### Features

* restore persistent BLE session with event-driven state updates ([49b9d81](https://github.com/roquerodrigo/ha-ttlock-ble/commit/49b9d81d4720e3154eee7c8298939a99bcb98b18))

## [2.0.0](https://github.com/roquerodrigo/ha-ttlock-ble/compare/v1.1.0...v2.0.0) (2026-05-12)


### ⚠ BREAKING CHANGES

* the operation event entity is gone. Push-driven event automations need to be replaced with state-change triggers on the lock entity.

### Features

* switch to on-demand BLE sessions to save lock battery ([54e51a5](https://github.com/roquerodrigo/ha-ttlock-ble/commit/54e51a55f0c23d8e6ddf66c574f34c98af9e21ab))

## [1.1.0](https://github.com/roquerodrigo/ha-ttlock-ble/compare/v1.0.0...v1.1.0) (2026-05-12)


### Features

* add Bluetooth connectivity binary sensor per lock ([dd9a536](https://github.com/roquerodrigo/ha-ttlock-ble/commit/dd9a536467fd6d201249fd8d4ab43c37092cbf10))
* **binary_sensor:** add Bluetooth icon to the connection sensor ([e4118cd](https://github.com/roquerodrigo/ha-ttlock-ble/commit/e4118cdc0780f2e02074660a29d072208656d4f8))

## [1.0.0](https://github.com/roquerodrigo/ha-ttlock-ble/compare/v0.1.2...v1.0.0) (2026-05-11)


### ⚠ BREAKING CHANGES

* the integration's domain changes from `integration_blueprint` (the prior template-fork release line, versions 0.1.x) to `ttlock_ble`. Existing installs from the template phase cannot upgrade in place; remove the old entry and add the new TTLock BLE integration.

### Features

* TTLock BLE Home Assistant integration ([67becd1](https://github.com/roquerodrigo/ha-ttlock-ble/commit/67becd1e652537a6df4ba78ba837d38a51450426))


### Bug Fixes

* **deps:** restore serialx (imported at module load by HA usb component) ([032875c](https://github.com/roquerodrigo/ha-ttlock-ble/commit/032875ccc792613a0384bd23cfbf80952766d5b1))

## [0.1.2](https://github.com/roquerodrigo/ha-ttlock-ble/compare/v0.1.1...v0.1.2) (2026-05-11)


### Dependencies

* bump Home Assistant to 2026.5.1 ([2ee9412](https://github.com/roquerodrigo/ha-ttlock-ble/commit/2ee9412994763b3e29611de78f1a0108ba02d258))

## [0.1.1](https://github.com/roquerodrigo/ha-ttlock-ble/compare/v0.1.0...v0.1.1) (2026-05-09)


### Dependencies

* bump mypy and pytest-homeassistant-custom-component ([9b4e67d](https://github.com/roquerodrigo/ha-ttlock-ble/commit/9b4e67d13ad21ee7ee2010e89d1444af0a30261c))


### Documentation

* standardize CODE_STYLE.md template ([9877550](https://github.com/roquerodrigo/ha-ttlock-ble/commit/9877550c96ac032a5d170fcaa01d593742b35dad))
* standardize CODE_STYLE.md template ([1b69040](https://github.com/roquerodrigo/ha-ttlock-ble/commit/1b69040a6954fb942dc6b74657994df4e0a075da))
