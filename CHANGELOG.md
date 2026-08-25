# Changelog

## [3.6.1](https://github.com/roquerodrigo/ha-ttlock-ble/compare/v3.6.0...v3.6.1) (2026-08-25)


### Bug Fixes

* **advertisement:** keep the known state when the lock is dormant ([e9163c0](https://github.com/roquerodrigo/ha-ttlock-ble/commit/e9163c0b9a6f579fbef16ae62e1c979b5b14bd00))


### Dependencies

* bump ttlock-ble to 0.2.0 ([06c3c14](https://github.com/roquerodrigo/ha-ttlock-ble/commit/06c3c1425a7d3e113d49cefa2955bf6b81663396))

## [3.6.0](https://github.com/roquerodrigo/ha-ttlock-ble/compare/v3.5.0...v3.6.0) (2026-08-24)


### Features

* **hacs:** ship the install zip with every release ([9802922](https://github.com/roquerodrigo/ha-ttlock-ble/commit/9802922a5f79e7f3867b23c372482c48eb9eebac))


### Development Dependencies

* **deps-dev:** bump the python-deps group across 1 directory with 5 updates ([20d4149](https://github.com/roquerodrigo/ha-ttlock-ble/commit/20d41494f30afcf9656a8d769be005bcf58afa00))


### Documentation

* normalize the README header layout ([698bb46](https://github.com/roquerodrigo/ha-ttlock-ble/commit/698bb4680620a3ae9a4d33e4f14abf47a59f0e87))

## [3.5.0](https://github.com/roquerodrigo/ha-ttlock-ble/compare/v3.4.0...v3.5.0) (2026-08-07)


### Features

* **options:** make the reconnect cooldown configurable and add a permanent connection mode ([d5182a3](https://github.com/roquerodrigo/ha-ttlock-ble/commit/d5182a36fd588ad23dd5aa07cdd340336f8b68e0))


### Bug Fixes

* keep the lock state when the operation-log read fails ([566f2ab](https://github.com/roquerodrigo/ha-ttlock-ble/commit/566f2ab52fc6d7b6a4a9518ac1bb619502948c16)), closes [#74](https://github.com/roquerodrigo/ha-ttlock-ble/issues/74)
* remove registry devices for locks that leave the entry's key set ([2e43dea](https://github.com/roquerodrigo/ha-ttlock-ble/commit/2e43dea91481ed0d29df881dfb1bf7ffca6d3110))


### Code Refactoring

* drop dead API surface and hoist record-type sets to module level ([c430338](https://github.com/roquerodrigo/ha-ttlock-ble/commit/c4303383e0dc7810c114a8307ad78cac26657f60))


### Dependencies

* bump homeassistant to 2026.8.0 with its matching test harness ([e69a570](https://github.com/roquerodrigo/ha-ttlock-ble/commit/e69a5704f9f53e7e2f013ac5751135d40ebe3ace))


### Documentation

* align README, CODE_STYLE and CLAUDE.md with the actual codebase ([af29a08](https://github.com/roquerodrigo/ha-ttlock-ble/commit/af29a080cb2473e8538b0a8867457e92fcd1c9dd))


### Continuous Integration

* run checks on pull requests targeting any branch ([73bea78](https://github.com/roquerodrigo/ha-ttlock-ble/commit/73bea78dd94a4ee8f6051b468dab7a0888cb5f4b))
* run code scanning on pull requests targeting any branch ([20e0d71](https://github.com/roquerodrigo/ha-ttlock-ble/commit/20e0d719703f2b5c012749261f32d64024765b4e))


### Miscellaneous Chores

* repair scripts/setup and align local tooling with the uv workflow ([a984db9](https://github.com/roquerodrigo/ha-ttlock-ble/commit/a984db92e23dc1f1db6953c02083d66537ce9334))
* sync uv.lock with the 3.4.0 release ([79b5f07](https://github.com/roquerodrigo/ha-ttlock-ble/commit/79b5f079a01fe8e7b7f5388e824024e550494e61))

## [3.4.0](https://github.com/roquerodrigo/ha-ttlock-ble/compare/v3.3.0...v3.4.0) (2026-08-05)


### Features

* **lock:** report the locking and unlocking transitional states ([8a91f23](https://github.com/roquerodrigo/ha-ttlock-ble/commit/8a91f2338908fc6886450b299c55dead7bde715f))


### Bug Fixes

* **api:** stop classifying every cloud failure as bad credentials ([b311efc](https://github.com/roquerodrigo/ha-ttlock-ble/commit/b311efc8c11aef4e798e92cc3dc5782ca590b72e))
* **binary-sensor:** author the translation key the entity actually asks for ([38db5d5](https://github.com/roquerodrigo/ha-ttlock-ble/commit/38db5d52d332bf129203d954e3d308e093141984))
* **config-flow:** keep the unique id in step with a reconfigured MAC ([0a7f8f7](https://github.com/roquerodrigo/ha-ttlock-ble/commit/0a7f8f79f678b1a9b23cfb20f8d3d9b42a261b57))
* **config-flow:** map key-sync failures to form errors ([9db3069](https://github.com/roquerodrigo/ha-ttlock-ble/commit/9db30693174612ade2661c03d8f38b89e85e19da))
* **config-flow:** reject credentials for a different account on reauth ([20798f0](https://github.com/roquerodrigo/ha-ttlock-ble/commit/20798f08ecd987652fffd8dd545ba5830dc1bb65))
* **config-flow:** run the lock-collision check on the cloud path too ([eaf96fb](https://github.com/roquerodrigo/ha-ttlock-ble/commit/eaf96fbf771dcddbcd3669cd967aa2c9ea8400f0))
* **connection:** bound the operation-log fetch ([343a999](https://github.com/roquerodrigo/ha-ttlock-ble/commit/343a99906a261a4f20c18d32ea81bb9e92be8f97))
* **connection:** refuse to open a BLE session after stop ([8f28b08](https://github.com/roquerodrigo/ha-ttlock-ble/commit/8f28b08c076c259a26f598d7ff2b707bcf29b71a))
* **connection:** report the BLE drop as soon as it happens ([7b88c91](https://github.com/roquerodrigo/ha-ttlock-ble/commit/7b88c912f307bb73be1c731a47289770eedaddc8))
* **coordinator:** seed the operation log per lock, on success ([80efc78](https://github.com/roquerodrigo/ha-ttlock-ble/commit/80efc7834d815ec771ba83fb537a0a6ed95058a6))
* **diagnostics:** redact the cloud account name from the entry title ([7a71597](https://github.com/roquerodrigo/ha-ttlock-ble/commit/7a71597e8e070446f97ba1ea0c32b867d6365d00))
* **event:** stop publishing keypad passcodes as event attributes ([a5d46b6](https://github.com/roquerodrigo/ha-ttlock-ble/commit/a5d46b662a17f68e3aa4d692b3a10df4c11eafd3))
* **init:** register teardown on the entry so failed setup cleans up ([6ddd446](https://github.com/roquerodrigo/ha-ttlock-ble/commit/6ddd446e59769df835fbfd309219481c81962191))
* **lock:** always clear the transitional state when a command ends ([179dc83](https://github.com/roquerodrigo/ha-ttlock-ble/commit/179dc83bdb10a9b2674bdbb53da761a9bfab436b))
* **lock:** compare the bolt state by value, not identity ([926c5a4](https://github.com/roquerodrigo/ha-ttlock-ble/commit/926c5a4cf2cfa392925318a783c6bd0dc59cdbb0))
* **lock:** serialize commands at the entity, not only on the wire ([89ff557](https://github.com/roquerodrigo/ha-ttlock-ble/commit/89ff557fe9206c7c824128136f6a238f965e59f0))
* **manual-key:** normalise the MAC before the advertisement cross-check ([eccbc73](https://github.com/roquerodrigo/ha-ttlock-ble/commit/eccbc73f3eb69e267df8d50e45f0c3f0685ef35f))


### Code Refactoring

* **coordinator:** drop the reachability flag nothing could use ([276e551](https://github.com/roquerodrigo/ha-ttlock-ble/commit/276e551145517b58f5b19096fd76dc156bf671ae))
* **event:** type the event attributes and hoist the event types ([3314a54](https://github.com/roquerodrigo/ha-ttlock-ble/commit/3314a5484bc2f316d7ac17e78f1e9ced5d920017))


### Dependencies

* **ttlock-ble:** bump to 0.1.10 ([b99d77e](https://github.com/roquerodrigo/ha-ttlock-ble/commit/b99d77e700c1be121aca490544f7bdda9ff1a2c6))


### Development Dependencies

* **deps-dev:** bump ruff ([3e6ab68](https://github.com/roquerodrigo/ha-ttlock-ble/commit/3e6ab68233d186adcd65c72e54a4357b4e288adb))


### Documentation

* **claude:** record the invariants these fixes introduced ([b4fabd4](https://github.com/roquerodrigo/ha-ttlock-ble/commit/b4fabd446b572b81cdb0472359e11fff104e1fa0))
* **code-style:** sync the style contract with the code it governs ([7f1741a](https://github.com/roquerodrigo/ha-ttlock-ble/commit/7f1741a794752c10a6b58db0003a5ab6416832e7))


### Tests

* **lock:** assert the post-command log read, and stop sleeping through it ([96e48c1](https://github.com/roquerodrigo/ha-ttlock-ble/commit/96e48c123472c62507e8668b0576ba5d3f8164aa))
* **lock:** build the push event through the SDK decoder ([872b945](https://github.com/roquerodrigo/ha-ttlock-ble/commit/872b945d4ffca7f4b81a31b5276ad9c7ddd2d59c))


### Miscellaneous Chores

* **deps-dev:** bump ruff to 0.16.0 ([17005ad](https://github.com/roquerodrigo/ha-ttlock-ble/commit/17005ad1c4f9401ee49c150808e89c18e4fc70de))
* **deps-dev:** bump the python-deps group across 1 directory with 2 updates ([144b809](https://github.com/roquerodrigo/ha-ttlock-ble/commit/144b809d4d662341cec3c0f771d04dc5d82c06e6))
* move CI to the shared workflows repository ([1ed6573](https://github.com/roquerodrigo/ha-ttlock-ble/commit/1ed6573e8f4caa0455851c7f67ce0e47e665eff1))
* release on every conventional commit type ([01ca6dc](https://github.com/roquerodrigo/ha-ttlock-ble/commit/01ca6dcd6cad9874fd104908597083a0304a7e20))

## [3.3.0](https://github.com/roquerodrigo/ha-ttlock-ble/compare/v3.2.3...v3.3.0) (2026-07-30)


### Features

* **config-flow:** add a lock key by hand, without a cloud account ([80f5b14](https://github.com/roquerodrigo/ha-ttlock-ble/commit/80f5b14e8a8ebc683da51c42c3050e39d49806d4)), closes [#48](https://github.com/roquerodrigo/ha-ttlock-ble/issues/48)

## [3.2.3](https://github.com/roquerodrigo/ha-ttlock-ble/compare/v3.2.2...v3.2.3) (2026-07-29)


### Bug Fixes

* track lock state from the lock's BLE advertisements ([40a908e](https://github.com/roquerodrigo/ha-ttlock-ble/commit/40a908e1a235a6224eb13d7499efb895504073a3)), closes [#42](https://github.com/roquerodrigo/ha-ttlock-ble/issues/42)


### Dependencies

* bump ttlock-ble to 0.1.8 ([6b41517](https://github.com/roquerodrigo/ha-ttlock-ble/commit/6b41517fd711e389ccf82e4fb9419edc14213339))

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
