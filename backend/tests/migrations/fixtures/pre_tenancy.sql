INSERT INTO users (id, normalized_email, display_name, status, system_role)
VALUES
    (1001, 'alpha-owner@example.test', 'Alpha owner', 'active', 'ordinary_user'),
    (1002, 'beta-owner@example.test', 'Beta owner', 'active', 'ordinary_user');

INSERT INTO households (id, name, created_by_user_id)
VALUES
    (2001, 'Alpha household', 1001),
    (2002, 'Beta household', 1002);

INSERT INTO household_memberships (household_id, user_id, role, status)
VALUES
    (2001, 1001, 'owner', 'active'),
    (2002, 1002, 'owner', 'active');

INSERT INTO operation_runs (
    id,
    trace_id,
    run_type,
    status,
    triggered_by_user_id,
    household_id,
    warnings,
    artifact_references
)
VALUES
    (3001, 'migration-alpha', 'migration_fixture', 'succeeded', 1001, 2001, '[]'::json, '[]'::json),
    (3002, 'migration-beta', 'migration_fixture', 'succeeded', 1002, 2002, '[]'::json, '[]'::json);

INSERT INTO audit_events (
    id,
    actor_user_id,
    household_id,
    action,
    target_type,
    target_id,
    metadata
)
VALUES
    (3101, 1001, 2001, 'migration.fixture', 'household', '2001', '{}'::json),
    (3102, 1002, 2002, 'migration.fixture', 'household', '2002', '{}'::json);

INSERT INTO household_profiles (id, name, current_version)
VALUES (4001, 'Historical shared profile', 1);

INSERT INTO household_profile_versions (
    id,
    profile_id,
    version,
    members,
    planning_household_size,
    max_cooking_time_minutes,
    allergens,
    excluded_ingredients,
    dietary_preferences,
    health_preferences,
    nutrition_targets,
    available_ingredients,
    pricing_mode
)
VALUES (
    4101,
    4001,
    1,
    '[]'::json,
    2,
    45,
    '[]'::json,
    '[]'::json,
    '[]'::json,
    '[]'::json,
    '{}'::json,
    '[]'::json,
    'fixture'
);

INSERT INTO meal_plans (
    id,
    start_date,
    end_date,
    day_count,
    household_size,
    pricing_mode,
    purchase_total_sgd,
    constraints,
    warnings,
    household_profile_id,
    household_profile_version
)
VALUES
    (5001, '2026-09-01', '2026-09-07', 7, 2, 'fixture', 42.00, '{}'::json, '[]'::json, 4001, 1),
    (5002, '2026-09-08', '2026-09-14', 7, 2, 'fixture', 48.00, '{}'::json, '[]'::json, 4001, 1);

INSERT INTO agent_sessions (
    id,
    status,
    parser_provider,
    constraints,
    missing_fields,
    clarification_questions,
    acknowledged_unknown_quantities,
    plan_id
)
VALUES
    (6001, 'planned', 'fixture', '{}'::json, '[]'::json, '[]'::json, '[]'::json, 5001),
    (6002, 'planned', 'fixture', '{}'::json, '[]'::json, '[]'::json, '[]'::json, 5002);

INSERT INTO agent_messages (id, session_id, role, content)
VALUES
    (6101, 6001, 'user', 'historical alpha request'),
    (6102, 6002, 'user', 'historical beta request');

INSERT INTO agent_runs (
    id,
    agent_session_id,
    actor_user_id,
    household_id,
    idempotency_key,
    intent,
    status,
    input_digest,
    context_version,
    deadline_at
)
VALUES
    (7001, 6001, 1001, NULL, 'legacy-alpha', 'plan', 'committed', repeat('a', 64), 1, '2026-09-01T00:02:00Z'),
    (7002, 6002, 1002, NULL, 'legacy-beta', 'plan', 'committed', repeat('b', 64), 1, '2026-09-08T00:02:00Z');
