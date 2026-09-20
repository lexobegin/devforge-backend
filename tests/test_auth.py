# tests/test_auth.py
"""Tests del módulo de autenticación."""

import pytest
from httpx import AsyncClient


# ======================================================================
# Registro
# ======================================================================
@pytest.mark.asyncio
async def test_registro_ok(client: AsyncClient):
    r = await client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "Ana Torres",
            "email": "ana@example.com",
            "password": "password123",
            "rol": "DESARROLLADOR",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["email"] == "ana@example.com"
    assert data["nombre_completo"] == "Ana Torres"
    assert data["rol"] == "DESARROLLADOR"
    assert data["activo"] is True
    # Nunca debe exponerse el hash
    assert "password" not in data
    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_registro_email_duplicado(client: AsyncClient):
    payload = {
        "nombre_completo": "Carlos",
        "email": "carlos@example.com",
        "password": "password123",
    }
    r1 = await client.post("/api/v1/auth/registro", json=payload)
    assert r1.status_code == 201

    r2 = await client.post("/api/v1/auth/registro", json=payload)
    assert r2.status_code == 409
    assert "email" in r2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_registro_password_corta(client: AsyncClient):
    r = await client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "Test",
            "email": "test@example.com",
            "password": "123",   # < 8 caracteres
        },
    )
    assert r.status_code == 422


# ======================================================================
# Login
# ======================================================================
@pytest.mark.asyncio
async def test_login_ok(client: AsyncClient, usuario_creado: dict):
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": usuario_creado["email"], "password": "password123"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["usuario"]["email"] == usuario_creado["email"]


@pytest.mark.asyncio
async def test_login_password_incorrecta(client: AsyncClient, usuario_creado: dict):
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": usuario_creado["email"], "password": "mal"},
    )
    assert r.status_code == 401
    # Mensaje genérico: no debe revelar si el email existe o no
    assert "credenciales" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_email_inexistente(client: AsyncClient):
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "nadie@example.com", "password": "password123"},
    )
    assert r.status_code == 401


# ======================================================================
# /me
# ======================================================================
@pytest.mark.asyncio
async def test_me_ok(client: AsyncClient, auth_headers: dict, usuario_creado: dict):
    r = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["email"] == usuario_creado["email"]


@pytest.mark.asyncio
async def test_me_sin_token(client: AsyncClient):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_token_invalido(client: AsyncClient):
    r = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer token.falso.aqui"},
    )
    assert r.status_code == 401


# ======================================================================
# Refresh
# ======================================================================
@pytest.mark.asyncio
async def test_refresh_ok(client: AsyncClient, usuario_creado: dict):
    r_login = await client.post(
        "/api/v1/auth/login",
        json={"email": usuario_creado["email"], "password": "password123"},
    )
    refresh_token = r_login.json()["refresh_token"]

    r = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_refresh_con_access_token(client: AsyncClient, usuario_creado: dict):
    """Un access token NO debe servir como refresh token."""
    r_login = await client.post(
        "/api/v1/auth/login",
        json={"email": usuario_creado["email"], "password": "password123"},
    )
    access_token = r_login.json()["access_token"]

    r = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert r.status_code == 401


# ======================================================================
# Cambio de contraseña
# ======================================================================
@pytest.mark.asyncio
async def test_cambiar_password_ok(client: AsyncClient, auth_headers: dict):
    r = await client.post(
        "/api/v1/auth/cambiar-password",
        headers=auth_headers,
        json={
            "password_actual": "password123",
            "password_nueva": "nuevaPassword456",
        },
    )
    assert r.status_code == 204

    # Login con la nueva contraseña debe funcionar
    r2 = await client.post(
        "/api/v1/auth/login",
        json={"email": "juan@example.com", "password": "nuevaPassword456"},
    )
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_cambiar_password_actual_incorrecta(
    client: AsyncClient, auth_headers: dict
):
    r = await client.post(
        "/api/v1/auth/cambiar-password",
        headers=auth_headers,
        json={
            "password_actual": "mal",
            "password_nueva": "otraPassword123",
        },
    )
    assert r.status_code == 400