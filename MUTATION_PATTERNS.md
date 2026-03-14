# Mutation Testing Patterns Guide

This document describes common code mutations that automated testing cannot catch (despite 100% code coverage) and patterns for writing tests that do catch them.

## Why Mutation Testing Matters

100% line coverage does NOT mean tests are effective. A test can:
- ✓ Execute every line
- ✓ Pass successfully
- ✗ Fail to catch subtle logic errors

**Example**: A test passes when `x == 5` but wouldn't catch if code changed to `x != 5`.

## Common Mutation Types

### 1. Operator Mutations

**Vulnerable Code**:
```python
if timeout_ms >= 1000:
    do_something()
```

**Problem**: Tests might pass if they never test exactly at the boundary (1000ms).

**Mutations That Survive**:
- `>=` → `>` (off-by-one error)
- `>=` → `<=` (logic inversion)
- `<` → `<=` (boundary miss)

**How to Test**:
```python
def test_timeout_boundary():
    """Test exact boundary value."""
    # Test AT the boundary
    assert handle_timeout(1000) is True
    # Test JUST BELOW the boundary
    assert handle_timeout(999) is False
    # Test ABOVE the boundary
    assert handle_timeout(1001) is True
```

**Pattern**: Always test boundary values explicitly, not just ranges.

---

### 2. String Operations

**Vulnerable Code**:
```python
def _roles_from_claims(claims):
    role_str = claims.get("role", "")
    roles = role_str.split(",")
    return frozenset(roles)
```

**Problem**: Code doesn't strip whitespace; tests might use clean strings.

**Mutations That Survive**:
- Missing `.strip()` call
- Missing `.lower()` call
- Wrong separator (`,` vs `;`)

**How to Test**:
```python
def test_roles_with_whitespace():
    """Roles must handle whitespace."""
    # Simulate real-world data with extra spaces
    result = _roles_from_claims({"role": "  admin  ,  operator  "})
    # Test will FAIL if strip() is missing
    assert result == frozenset({"admin", "operator"})

def test_roles_case_insensitive():
    """Roles should be case-normalized."""
    result = _roles_from_claims({"role": "ADMIN,Operator"})
    # Test will FAIL if lower() is missing
    assert result == frozenset({"admin", "operator"})
```

**Pattern**: Test with realistic, messy input. Include whitespace, mixed case, etc.

---

### 3. Boolean Logic Mutations

**Vulnerable Code**:
```python
def can_perform_action(user, resource):
    if user.role == "admin" or user.role == "operator":
        return True
    return False
```

**Problem**: Tests might check happy path but miss one condition.

**Mutations That Survive**:
- `or` → `and` (both conditions required)
- `==` → `!=` (inverted logic)
- Missing condition entirely

**How to Test**:
```python
def test_role_permissions():
    """Test both conditions independently."""
    admin_user = User(role="admin")
    operator_user = User(role="operator")
    viewer_user = User(role="viewer")

    # If logic was mutated to AND, admin alone would fail
    assert can_perform_action(admin_user, resource) is True

    # If logic was mutated to AND, operator alone would fail
    assert can_perform_action(operator_user, resource) is True

    # Both should not grant access to viewers
    assert can_perform_action(viewer_user, resource) is False
```

**Pattern**: Test EACH condition independently, not just combinations.

---

### 4. Default/Fallback Values

**Vulnerable Code**:
```python
def get_user_role(token):
    claims = verify_jwt(token)
    role = claims.get("role", "viewer")  # Default to viewer
    return role
```

**Problem**: Tests might never exercise the fallback case.

**Mutations That Survive**:
- Wrong default value (`"admin"` instead of `"viewer"`)
- Missing default entirely (returns None)
- Wrong fallback variable

**How to Test**:
```python
def test_missing_role_defaults_to_viewer():
    """Missing role must default to viewer, not admin."""
    token = create_token(claims={})  # No role claim

    role = get_user_role(token)

    # Test FAILS if default is wrong
    assert role == "viewer"
    assert role != "admin"
    assert role is not None
```

**Pattern**: Always test the fallback path explicitly.

---

### 5. Comparison Operators

**Vulnerable Code**:
```python
def is_rate_limited(count, max_allowed=100):
    return count > max_allowed
```

**Problem**: Off-by-one errors in comparisons are common.

**Mutations That Survive**:
- `>` → `>=` (counts 100 as limited when it shouldn't be)
- `>` → `<` (inverted logic)
- `==` → `!=` (wrong condition)

**How to Test**:
```python
def test_rate_limit_boundaries():
    """Test exact limit boundaries."""
    # At the limit - should NOT be rate limited
    assert is_rate_limited(100, 100) is False

    # Just over limit - should be rate limited
    assert is_rate_limited(101, 100) is True

    # Way under limit
    assert is_rate_limited(50, 100) is False
```

**Pattern**: Test AT, JUST BELOW, and JUST ABOVE boundaries.

---

### 6. Early Returns / Control Flow

**Vulnerable Code**:
```python
def validate_config(config):
    if config.mode not in {"dev", "prod"}:
        raise ValueError("Invalid mode")

    if config.mode == "prod":
        if not config.secret_key:
            raise ValueError("Secret key required in prod")
```

**Problem**: If the second check is skipped with early return, tests might miss it.

**Mutations That Survive**:
- Early return added (`if mode != "prod": return`)
- Early return removed
- Wrong condition in return

**How to Test**:
```python
def test_prod_mode_requires_secret():
    """Prod mode MUST validate secret key."""
    config = Config(mode="prod", secret_key=None)

    # Should raise - test would FAIL if validation skipped
    with pytest.raises(ValueError, match="Secret key"):
        validate_config(config)

def test_non_prod_mode_ignores_secret():
    """Non-prod modes don't need secret."""
    config = Config(mode="dev", secret_key=None)

    # Should not raise
    validate_config(config)
```

**Pattern**: Test that each validation path is actually executed.

---

### 7. Collection Operations

**Vulnerable Code**:
```python
def is_admin(user):
    return user.role in ["admin", "superuser"]
```

**Problem**: Tests might miss if `in` operator is changed to other logic.

**Mutations That Survive**:
- `in` → `not in`
- Missing elements from list
- `in` → equality check
- Wrong collection type (set vs list)

**How to Test**:
```python
def test_admin_roles_exact():
    """Only admin and superuser are admin roles."""
    assert is_admin(User(role="admin")) is True
    assert is_admin(User(role="superuser")) is True

    # Non-admin roles must return False (catches NOT IN mutation)
    assert is_admin(User(role="operator")) is False
    assert is_admin(User(role="viewer")) is False
    assert is_admin(User(role="")) is False
```

**Pattern**: Test members AND non-members of collections.

---

### 8. Numeric Mutations

**Vulnerable Code**:
```python
def retry_with_backoff(attempt):
    delay = 2 ** attempt  # Exponential backoff
    return delay
```

**Problem**: Wrong exponent or base survives if tests don't verify exact values.

**Mutations That Survive**:
- `2 ** attempt` → `2 * attempt` (linear vs exponential)
- `2 ** attempt` → `3 ** attempt` (different base)
- Off-by-one in exponent

**How to Test**:
```python
def test_exponential_backoff():
    """Backoff must be exponential, not linear."""
    assert retry_with_backoff(0) == 1    # 2^0
    assert retry_with_backoff(1) == 2    # 2^1
    assert retry_with_backoff(2) == 4    # 2^2 (not 4 from 2*2)
    assert retry_with_backoff(3) == 8    # 2^3 (not 6 from 2*3)
    assert retry_with_backoff(4) == 16   # 2^4 (not 8 from 2*4)
```

**Pattern**: Test specific, calculated values, not just ranges.

---

## Testing Checklist

When writing tests, ensure you:

- [ ] **Boundary Testing**: Test AT boundaries, not just ranges
  - `x == 5`, `x < 5`, `x > 5`
- [ ] **String Normalization**: Test with whitespace, mixed case
  - `"  VALUE  "`, `"MixedCase"`, `""`
- [ ] **Boolean Logic**: Test each condition independently
  - If `A or B`, test A alone, B alone, neither
- [ ] **Defaults**: Explicitly test fallback paths
  - Missing values, None values, empty values
- [ ] **Comparisons**: Test AT limit values
  - `count == limit`, `count < limit`, `count > limit`
- [ ] **Control Flow**: Verify all validation paths execute
  - Use assertions to confirm flow
- [ ] **Collections**: Test members AND non-members
  - `in set`, `not in set`
- [ ] **Numeric**: Test calculated values, not estimates
  - `2**4 == 16`, not just "correct size"

---

## Real Examples from Project

### ✅ Good: test_auth_edge_cases.py

```python
def test_jwt_rejects_none_algorithm_case_insensitive():
    """Catches mutation: case normalization"""
    config = ServerConfig(
        auth=AuthConfig(
            mode="jwt",
            jwt_public_key_pem="key",
            jwt_algorithms=[  "HS256", "NONE"],  # UPPERCASE
            worker_bearer_token="token",
        )
    )
    # Test FAILS if upper case isn't normalized to lower
    with pytest.raises(ValueError, match="none"):
        _validate_auth_config(config)
```

### ✅ Good: test_cli_validation.py

```python
def test_proxy_port_default_exact_8765():
    """Catches mutation: off-by-one in default"""
    args = _build_parser().parse_args(["proxy", "host", "23"])
    assert args.port == 8765
    assert args.port != 8764  # Catches 8764 mutation
    assert args.port != 8766  # Catches 8766 mutation
```

---

## How to Apply This in Code Reviews

When reviewing tests, ask:

1. **Is this boundary tested?**
   - If code has `if x > 5`, are 5, 4, 6 all tested?

2. **Would this test catch a negation?**
   - If code has `if check_valid()`, test `check_invalid()` too

3. **Is this fallback tested?**
   - If code has `or "default"`, test when first condition fails

4. **Are calculated values verified?**
   - Not "approximately correct", but EXACTLY correct

5. **Is this mutation-prone?**
   - Operator (`<` vs `<=`)?
   - String (`strip()`, `lower()`, etc.)?
   - Boolean logic (`and` vs `or`)?

---

## References

- **Mutation Testing Concept**: Tests validate correctness, not just execution
- **Related Tools**: mutmut, cosmic-ray, pitest
- **Project Coverage**: 100% line coverage + these patterns = 85%+ mutation kill rate

---

**Last Updated**: 2026-03-13
**Maintained By**: Development Team
