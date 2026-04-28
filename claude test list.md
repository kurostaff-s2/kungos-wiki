<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# what are the suite of test needed to thoroughly test all of the functionalities and data flow, CRUD operations for both backend and front end

Based on the two documents already analyzed, here is the complete, project-specific test suite tailored to every layer of the KungOS + CAFE_PLATFORM architecture.

## Testing Philosophy for This Stack

The stack has four distinct test targets: the Django backend, the React manager dashboard, the Rust station-service, and the Tauri station-shell. Each target has a different risk profile — backend wallet logic is billing-critical, the timer engine is trust-critical, and the WebSocket layer is availability-critical. Tests are organized by the **pyramid principle**: many unit tests at the bottom, fewer integration tests in the middle, minimal E2E tests at the top.[^1][^2]

***

## Backend Tests (`pytest-django`)

### `test_wallet.py` — Billing Critical

```python
# Wallet Integrity
test_wallet_create_on_customer_register()          # WAL id format, OneToOne FK
test_wallet_initial_balance_is_zero()
test_wallet_can_spend_returns_false_when_frozen()
test_wallet_can_spend_returns_false_when_balance_insufficient()
test_wallet_can_spend_returns_true_when_active_and_funded()

# Recharge
test_recharge_increments_balance_correctly()
test_recharge_creates_transaction_record_type_recharge()
test_recharge_updates_total_recharged_field()
test_recharge_below_minimum_100_rejected()          # TenantConfig.walletcfg.minrecharge
test_recharge_above_maximum_10000_rejected()        # TenantConfig.walletcfg.maxbalance

# Spend
test_spend_decrements_balance_with_row_level_lock()
test_spend_creates_transaction_record_type_spend()
test_spend_updates_total_spent_field()
test_concurrent_spend_no_double_debit()             # simulate 2 concurrent endSession calls
test_spend_on_frozen_wallet_raises_WalletFrozen()

# Points
test_increment_points_uses_F_expression_not_read_modify_write()
test_loyalty_rate_applied_correctly_from_tenant_config()

# Refund
test_refund_restores_balance()
test_refund_creates_transaction_type_refund()
test_refund_idempotent_via_reference_id()           # same refund twice = no double credit

# Prize Winnings
test_tournament_prize_credited_to_wallet()
test_prize_transaction_type_is_prizewinnings()
test_prize_reference_type_is_tournament()

# Admin Adjustment
test_admin_adjustment_requires_staff_user()
test_adjustment_logged_with_createdby_field()

# Freeze / Close
test_freeze_wallet_blocks_all_spend()
test_close_wallet_blocks_recharge_and_spend()
```


### `test_session.py` — Timer \& Billing Critical

```python
# Session Start
test_start_session_creates_gamers_document_in_mongo()
test_start_session_locks_station_status_to_occupied()
test_start_session_walk_in_no_auth_allowed()
test_start_session_jwt_mode_requires_valid_cookie()
test_start_session_insufficient_balance_returns_400_INSUFFICIENT_BALANCE()
test_start_session_station_unavailable_returns_400_STATION_UNAVAILABLE()
test_start_session_emits_session_started_domain_event()
test_start_session_writes_outbox_event_in_same_transaction()
test_start_session_applies_membership_discount_titan()
test_start_session_applies_membership_discount_s_tier()
test_start_session_returns_effective_rate_in_response()

# Pause / Resume
test_pause_records_paused_at_timestamp()
test_pause_stores_accumulated_minutes_correctly()
test_resume_records_resumed_at_timestamp()
test_resume_on_non_paused_session_returns_400()
test_pause_on_already_paused_session_returns_400()

# Extend
test_extend_adds_minutes_to_session_end_time()
test_extend_checks_wallet_balance_before_extending()
test_extend_respects_maximum_session_minutes_480()

# Food Orders
test_add_food_to_session_appends_to_food_array()
test_food_charges_included_in_end_session_total()
test_food_order_requires_active_session()

# End Session
test_end_session_calculates_base_rate_correctly()
test_end_session_applies_peak_multiplier_within_hours()
test_end_session_applies_peak_multiplier_outside_hours()  # should be 1.00
test_end_session_applies_weekend_multiplier_on_saturday()
test_end_session_applies_weekend_multiplier_on_weekday()  # should be 1.00
test_end_session_enforces_minimum_charge_30_minutes()
test_end_session_debits_wallet_atomically()
test_end_session_frees_station_status_to_online()
test_end_session_sets_gamers_playerstatus_closed()
test_end_session_returns_points_earned_in_response()
test_end_session_emits_session_ended_domain_event()
test_end_session_reconciles_paused_time_excluded_from_billing()

# Expired Sessions
test_check_expired_sessions_closes_sessions_over_480_min()
test_check_expired_sessions_is_idempotent()
test_check_expired_sessions_skips_paused_sessions()

# Grace Period
test_grace_period_15_min_no_charge_for_short_sessions()
```


### `test_pricing.py`

```python
test_zone_144hz_base_rate_correct()
test_zone_240hz_base_rate_correct()
test_zone_vr_base_rate_correct()
test_peak_multiplier_applied_between_1800_2300()
test_peak_multiplier_not_applied_before_1800()
test_weekend_multiplier_applied_on_sunday()
test_calculate_charges_endpoint_returns_effectiverate()
test_pricing_scoped_to_bgcode_no_cross_tenant_bleed()
test_pricing_seed_command_creates_correct_rules()
```


### `test_customer_lookup.py`

```python
test_walk_in_lookup_returns_customer_and_wallet()
test_walk_in_lookup_creates_new_customer_if_not_found()
test_walk_in_lookup_returns_active_session_if_exists()
test_register_customer_creates_customuser_and_cafewalkin()
test_register_customer_already_exists_returns_200_status_exists()
test_jwt_auth_customer_profile_returns_membership_tier()
test_customer_lookup_rate_limited_after_N_requests()   # Gap 1 remediation
test_phone_format_validated_91XXXXXXXXXX()
```


### `test_tenant_isolation.py` — Security Critical

```python
test_tenant_collection_raises_TenantContextMissing_without_context()
test_bgcode_filter_applied_on_all_mongo_queries()
test_station_query_scoped_to_bgcode()
test_session_query_scoped_to_bgcode()
test_wallet_transactions_scoped_to_bgcode()
test_cross_tenant_station_access_blocked()
test_cross_tenant_session_access_blocked()
test_rls_policy_blocks_cross_bg_postgres_query()
test_tenant_config_loaded_from_db_not_hardcoded()
test_tenant_config_cached_with_ttl()
test_tenant_config_fallback_to_defaults_on_cache_miss()
```


### `test_auth.py`

```python
test_cookie_jwt_authentication_sets_httponly_cookie()
test_cookie_jwt_authentication_rejects_localStorage_token()
test_knox_tokens_return_401_after_migration()         # cutover validation
test_walk_in_endpoint_accessible_without_auth()
test_admin_endpoint_blocked_without_auth()
test_token_blacklisted_on_logout()
test_tenant_aware_token_carries_bgcode_entity_branch()
test_throttle_login_10_per_min()
test_throttle_otp_5_per_min()
test_throttle_anon_100_per_min()
```


### `test_outbox.py` — Consistency Critical

```python
test_wallet_debit_and_outbox_event_in_same_transaction()
test_outbox_event_marked_processed_after_handler_runs()
test_outbox_event_marked_failed_on_handler_exception()
test_failed_outbox_event_goes_to_dead_letter_queue()
test_outbox_processor_is_idempotent()                # process same event twice = no duplicate
test_outbox_replay_repairs_mongo_side_effect()
test_outbox_event_carries_bgcode_for_tenant_context()
```


### `test_websocket.py` — Gap 1 Implementation

```python
test_station_consumer_accepts_valid_jwt_connection()
test_station_consumer_rejects_expired_jwt()
test_station_consumer_rejects_missing_jwt()
test_heartbeat_accepted_within_15s()
test_heartbeat_rejected_when_gap_exceeds_30s()
test_session_start_command_delivered_to_station()
test_session_extend_command_delivered_to_station()
test_session_stop_command_delivered_to_station()
test_lease_applied_message_received_from_station()
test_broadcast_to_all_shells_for_same_station()
test_reconnect_triggers_state_resync()
```


### `test_station_mgmt.py`

```python
test_create_station_with_required_fields()
test_update_station_status_online_offline_maintenance()
test_get_stations_filtered_by_zone()
test_get_stations_filtered_by_branch()
test_station_seed_command_creates_correct_records()
test_station_registration_on_first_boot()
test_station_heartbeat_updates_last_seen()
```


### `test_permissions.py`

```python
test_cafedashboard_requires_accesslevel_1()
test_stationmanagement_full_requires_accesslevel_2()
test_pricingmanagement_requires_accesslevel_2()
test_walletrecharge_requires_accesslevel_1()
test_unauthenticated_gamers_endpoint_removed()
test_permission_check_resolves_once_per_request()   # no pandas, no re-query
test_accesslevel_serializer_includes_all_7_cafe_fields()
```


***

## Frontend Tests (`Vitest` + `React Testing Library`)

### `cafeSlice.test.js` — Redux State

```javascript
test_setCustomer_populates_currentCustomer_state()
test_setWalletBalance_updates_walletBalance_correctly()
test_setActiveSessions_replaces_sessions_array()
test_setCurrentSession_null_clears_session()
test_setDashboardOverview_updates_all_sub_fields()
test_loading_flags_set_true_on_start_false_on_complete()
test_no_direct_state_mutation_via_dispatch_only()
```


### `cafeApi.test.js` — API Layer Contract

```javascript
test_lookupCustomer_calls_POST_cafe_customer_lookup()
test_rechargeWallet_calls_POST_cafe_wallet_recharge()
test_startSession_calls_POST_cafe_sessions_start()
test_endSession_calls_POST_cafe_sessions_end()
test_getActiveSessions_calls_GET_with_branch_param()
test_getDashboardOverview_calls_GET_with_branch_param()
test_all_calls_go_through_cafeApi_not_direct_axios()
test_API_error_INSUFFICIENT_BALANCE_parsed_correctly()
test_API_error_SESSION_CONFLICT_parsed_correctly()
test_API_error_STATION_UNAVAILABLE_parsed_correctly()
test_API_error_RATE_LIMITED_parsed_correctly()
test_API_error_AUTH_EXPIRED_triggers_redirect_to_login()
```


### `CustomerLookup.test.jsx`

```javascript
test_phone_input_formats_to_91XXXXXXXXXX()
test_lookup_shows_customer_name_and_wallet_balance()
test_lookup_shows_active_session_badge_if_session_exists()
test_lookup_404_silently_creates_new_customer()
test_rate_limited_shows_too_many_requests_toast()
test_submit_disabled_while_customerLookupLoading_true()
```


### `SessionStart.test.jsx`

```javascript
test_shows_available_stations_from_redux_state()
test_insufficient_balance_opens_PaymentModal()
test_PaymentModal_recharge_success_retries_startSession()
test_station_unavailable_shows_pick_another_message()
test_session_loading_spinner_shown_while_setSessionLoading_true()
test_setCustomer_dispatched_after_successful_lookup()
test_setCurrentSession_dispatched_after_startSession_success()
```


### `SessionActive.test.jsx`

```javascript
test_SessionTimer_counts_down_from_session_start()
test_pause_button_calls_pauseSession_mutation()
test_resume_button_calls_resumeSession_mutation()
test_extend_insufficient_balance_opens_PaymentModal()
test_FoodOrderModal_adds_food_to_session()
test_empty_active_sessions_shows_no_active_sessions_message()
test_SESSION_CONFLICT_error_triggers_auto_refresh()
```


### `SessionEnd.test.jsx`

```javascript
test_shows_session_duration_total_minutes()
test_shows_session_charges_food_charges_total()
test_shows_wallet_balance_after_deduction()
test_shows_points_earned()
test_success_toast_shows_charged_amount()
test_setCurrentSession_null_dispatched_on_success()
test_getActiveSessions_invalidated_on_success()
test_station_freed_reflected_in_StationCard()
```


### `WalletBalance.test.jsx` / `WalletRecharge.test.jsx`

```javascript
test_displays_balance_from_redux_walletBalance()
test_displays_membership_tier_badge()
test_displays_transaction_history_list()
test_empty_history_shows_no_transactions_yet()
test_recharge_form_validates_minimum_amount()
test_recharge_success_updates_walletBalance_in_redux()
test_recharge_error_shows_error_message()
```


### `CafeDashboard.test.jsx`

```javascript
test_dashboard_polls_getDashboardOverview_every_10s()
test_polling_aborted_on_component_unmount()
test_StationCard_renders_each_station_from_overview()
test_RevenueChart_receives_revenue_prop()
test_ZoneUtilization_receives_utilization_prop()
test_403_redirects_with_toast_no_dashboard_access()
test_500_shows_error_banner()
test_dashboardLoading_true_shows_spinner()
```


### `permissions.test.js`

```javascript
test_CAFEDASHBOARD_permission_key_value_accesslevel()
test_PRICINGMANAGEMENT_requires_accesslevel_2()
test_page_redirects_on_insufficient_accesslevel()
test_permission_check_runs_on_mount_not_on_render()
```


### `queryKeys.test.js`

```javascript
test_cafe_wallet_balance_key_includes_walletId()
test_cafe_sessions_active_key_includes_branch()
test_cafe_dashboard_overview_key_includes_branch()
test_cafe_stations_detail_key_includes_stationId()
test_invalidateQueries_called_with_correct_key_after_mutation()
```


***

## Station Desktop Tests

### `station-service` (Rust — `cargo test`)

```rust
// Timer Engine
test_timer_uses_monotonic_clock_Instant()
test_timer_continues_during_cloud_disconnect()
test_timer_emits_tick_events_via_ipc()
test_timer_stops_cleanly_on_session_stop_command()
test_timer_accuracy_over_60_seconds()               // drift < 500ms

// Lease Management
test_sqlite_lease_persists_across_service_restart()
test_apply_lease_validates_hmac_signature()
test_apply_lease_rejects_replayed_command()          // seqno check
test_extend_lease_updates_ends_at_in_sqlite()
test_stop_lease_clears_sqlite_record()
test_lease_expired_auto_closes_session()

// IPC Named Pipe
test_pipe_accepts_connection_from_shell_only()       // ACL check
test_pipe_rejects_unknown_process()
test_request_response_via_correlation_id()
test_newline_delimited_json_envelope_parsed()
test_pipe_recovers_after_shell_restart()

// Game Launcher
test_launch_game_by_exe_path()
test_game_launched_with_CREATE_NO_WINDOW_flag()
test_game_launched_with_correct_working_directory()
test_launch_emits_game_launched_event()
test_exit_detected_by_process_watchdog()
test_exit_emits_game_exited_event()

// Process Watchdog
test_watchdog_polls_every_5s()
test_watchdog_detects_game_launch()
test_watchdog_detects_game_exit()
test_watchdog_blocks_task_manager_in_kiosk_mode()
test_watchdog_blocks_explorer_in_kiosk_mode()

// Offline Queue
test_events_queued_in_sqlite_when_cloud_disconnected()
test_batch_sync_on_reconnect_sends_all_queued_events()
test_batch_sync_preserves_event_order_by_seqno()
test_queued_events_cleared_after_successful_sync()

// Command Worker
test_commands_processed_in_order()
test_invalid_command_type_logged_not_crashed()
test_command_worker_retries_on_transient_failure()
```


### `station-shell` (Vitest inside Tauri)

```javascript
// WebSocket Client (cloud-ws.ts)
test_connects_to_wss_station_stationId_with_jwt()
test_CONNECTIVITY_LOST_emitted_on_disconnect()
test_CONNECTIVITY_RESTORED_emitted_on_reconnect()
test_exponential_backoff_on_reconnect()
test_command_messages_dispatched_to_stationStore()

// IPC Client (ipc-client.ts)
test_opens_named_pipe_to_cafe_station()
test_send_command_appends_newline_delimiter()
test_correlation_id_matches_response()
test_listen_events_emits_to_stationStore()

// stationStore (Zustand)
test_setCurrentSession_updates_store()
test_remainingSeconds_decremented_on_event_sessiontick()
test_clear_currentSession_on_command_stop()
test_kiosk_mode_toggled_on_command_kioskactivate()

// Login.jsx (QR flow — Gap 6)
test_QR_code_rendered_from_auth_token_hash()
test_polling_GET_auth_tokens_hash_status_every_2s()
test_QR_expires_after_60s_shows_regenerate_button()
test_successful_scan_transitions_to_SessionActive()

// SessionActive.jsx (station-shell)
test_TimerDisplay_shows_remaining_time_from_store()
test_TimerDisplay_turns_red_below_5_minutes()
test_ReconnectBanner_shown_on_CONNECTIVITY_LOST()
test_ReconnectBanner_hidden_on_CONNECTIVITY_RESTORED()

// Kiosk.jsx
test_enters_fullscreen_on_kioskactivate_command()
test_auto_logout_on_session_end()
```


***

## Integration Tests

### `test_full_session_lifecycle.py` — End-to-End Data Flow

```python
# Traces: phone lookup → wallet check → session start →
#         MongoDB gamers doc → pricing calc → session end →
#         wallet debit → outbox → transaction record
test_walk_in_full_lifecycle_no_auth()
test_registered_user_full_lifecycle_with_jwt()
test_session_with_food_orders_total_calculation()
test_session_paused_and_resumed_billing_excludes_pause()
test_session_extended_additional_charge_correct()
test_wallet_insufficient_mid_session_auto_close()
```


### `test_cross_brand_wallet.py`

```python
test_tournament_prize_credited_and_redeemable_at_cafe()
test_retail_purchase_debits_shared_wallet()
test_loyalty_points_accumulate_across_cafe_and_esports()
test_wallet_balance_consistent_across_brands()
```


### `test_websocket_station_integration.py`

```python
test_startSession_API_pushes_command_to_station_shell_via_ws()
test_station_heartbeat_keeps_connection_alive()
test_session_stop_command_reaches_station_shell()
test_station_lease_applied_received_by_cloud()
test_disconnect_triggers_offline_queue_on_service()
test_reconnect_syncs_queued_events_to_cloud()
```


### `test_outbox_integration.py`

```python
test_end_session_postgres_commit_triggers_mongo_side_effect()
test_mongo_write_failure_leaves_outbox_event_for_retry()
test_dead_letter_event_replayable_via_management_command()
```


***

## Security Tests

```python
# Injection & Boundary
test_phone_field_rejects_sql_injection()
test_wallet_amount_rejects_negative_values()
test_session_id_param_cannot_access_other_tenant_session()
test_station_id_param_cannot_access_other_tenant_station()

# Auth Bypass
test_gamers_endpoint_no_longer_accepts_unauthenticated_requests()
test_walk_in_endpoint_cannot_start_session_without_wallet_check()
test_jwt_token_from_wrong_bgcode_rejected()
test_hmac_signature_forgery_rejected_by_station_service()

# Tenant Bleed
test_bgcode_BG0001_cannot_read_BG0002_wallets()
test_bgcode_BG0001_cannot_start_session_on_BG0002_station()
test_rls_active_on_cafewallet_transactions_table()

# Rate Limiting
test_customer_lookup_rate_limited_at_threshold()
test_login_rate_limited_at_10_per_min()
```


***

## Test Infrastructure \& Conventions

| Concern | Tool | Rule |
| :-- | :-- | :-- |
| Backend runner | `pytest` + `pytest-django` | All tests use `@pytest.mark.django_db` |
| Backend fixtures | `conftest.py` per app | Seed `TenantConfig`, `CafeWallet`, `CafePricingRule` |
| MongoDB in tests | `mongomock` or test DB | Isolated `kuropurchase_test` collection with cleanup |
| Frontend runner | `Vitest` + `@testing-library/react` | No `act()` warnings; wrap async with `waitFor` |
| Frontend mocking | `vi.mock('../../api/cafeApi')` | Mock at module boundary, never at `fetch` level |
| Station Rust | `cargo test` with `#[cfg(test)]` modules | Use `tempfile` crate for SQLite in tests |
| WebSocket tests | `channels.testing.WebsocketCommunicator` | Async test with `@pytest.mark.asyncio` |
| CI gate | GitHub Actions (Phase 4) | All test suites must pass before merge to main |
| Test DB isolation | `@pytest.fixture(scope="function")` | Each test gets a fresh transaction, rolled back after |
| Outbox isolation | Override `CELERY_TASK_ALWAYS_EAGER = True` | Outbox processor runs synchronously in tests |

The most critical test chain to run in CI in order is: `test_tenant_isolation` → `test_auth` → `test_wallet` → `test_session` → `test_outbox` → `test_websocket` → `test_full_session_lifecycle`. Any failure in the earlier tests makes later tests meaningless since they all depend on tenant context and wallet integrity being correct.[^2][^1]
<span style="display:none">[^10][^11][^12][^13][^14][^15][^16][^17][^3][^4][^5][^6][^7][^8][^9]</span>

<div align="center">⁂</div>

[^1]: KungOS_v2.md

[^2]: CAFE_PLATFORM.md

[^3]: https://stackoverflow.com/questions/3215224/when-how-to-unit-test-crud-applications

[^4]: https://www.reddit.com/r/webdev/comments/qg9uzy/what_kind_of_test_should_i_write_in_a_crud_app/

[^5]: https://testrigor.com/blog/frontend-testing-vs-backend-testing/

[^6]: https://dev.to/romeuu/why-you-should-test-both-frontend-and-backend-48o5

[^7]: https://codesignal.com/learn/courses/automating-api-tests-with-cpp-1/lessons/testing-crud-operations-with-setup-and-teardown-in-cpp-1

[^8]: https://www.testscenario.com/full-stack-testing/

[^9]: https://csestudyzone.blogspot.com/2015/06/strategies-in-data-flow-testing-in.html

[^10]: https://github.com/KhorshedSagor/Api-automation-using-mocha-framework

[^11]: https://www.chiragr.com/blog/testing-strategies

[^12]: https://www.geeksforgeeks.org/software-testing/data-flow-testing/

[^13]: https://www.geeksforgeeks.org/software-testing/software-testing-web-application-testing-checklist-with-test-scenarios/

[^14]: https://demo.hotelinteractive.com/testing-process-in-full-stack-application/

[^15]: https://www.testbytes.net/blog/data-flow-testing/

[^16]: http://hackajob.com/talent/blog/writing-and-testing-crud

[^17]: https://www.joinfita.com/what-are-the-most-effective-testing-strategies-for-full-stack-apps/

