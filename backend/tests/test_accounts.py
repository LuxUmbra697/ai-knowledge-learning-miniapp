import pytest
from pydantic import ValidationError

from app.services.account_service import AccountCredentials, hash_password, verify_password


def test_passwords_use_salted_verifiable_hashes():
    first = hash_password("a-private-passphrase")
    second = hash_password("a-private-passphrase")
    assert first != second
    assert "a-private-passphrase" not in first
    assert verify_password("a-private-passphrase", first)
    assert not verify_password("wrong-password", first)


def test_bad_password_hash_is_rejected():
    assert not verify_password("password", "corrupt")
    assert not verify_password("password", "scrypt$999999999$8$1$a$b")


@pytest.mark.parametrize("data", [
    {"username": "bad name", "password": "long-password"},
    {"username": "user", "password": "short"},
    {"username": "user", "password": "long-password", "user_id": 1},
])
def test_identity_and_password_input_constraints(data):
    with pytest.raises(ValidationError):
        AccountCredentials.model_validate(data)
