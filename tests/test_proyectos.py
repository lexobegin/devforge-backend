# tests/test_proyectos.py
"""Tests del módulo de proyectos y miembros."""

import pytest
from httpx import AsyncClient


# ======================================================================
# Crear proyecto
# ======================================================================
@pytest.mark.asyncio
async def test_crear_proyecto_ok(client: AsyncClient, auth_headers: dict):
    r = await client.post(
        "/api/v1/proyectos",
        headers=auth_headers,
        json={"nombre": "Salud Universal", "descripcion": "Sistema del Ministerio"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["nombre"] == "Salud Universal"
    assert data["estado"] == "ACTIVO"
    assert data["id_propietario"] is not None


@pytest.mark.asyncio
async def test_crear_proyecto_sin_token(client: AsyncClient):
    r = await client.post(
        "/api/v1/proyectos",
        json={"nombre": "Sin token"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_crear_proyecto_nombre_vacio(client: AsyncClient, auth_headers: dict):
    r = await client.post(
        "/api/v1/proyectos",
        headers=auth_headers,
        json={"nombre": ""},
    )
    assert r.status_code == 422


# ======================================================================
# Listar y obtener
# ======================================================================
@pytest.mark.asyncio
async def test_listar_proyectos(client: AsyncClient, auth_headers: dict):
    # Crear 2 proyectos
    for n in ("Proyecto A", "Proyecto B"):
        await client.post(
            "/api/v1/proyectos",
            headers=auth_headers,
            json={"nombre": n},
        )

    r = await client.get("/api/v1/proyectos", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 2
    assert len(data["items"]) >= 2


@pytest.mark.asyncio
async def test_obtener_proyecto_con_miembros(client: AsyncClient, auth_headers: dict):
    r_crear = await client.post(
        "/api/v1/proyectos",
        headers=auth_headers,
        json={"nombre": "Con equipo"},
    )
    proyecto_id = r_crear.json()["id"]

    r = await client.get(f"/api/v1/proyectos/{proyecto_id}", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "miembros" in data
    assert len(data["miembros"]) == 1
    assert data["miembros"][0]["rol_en_proyecto"] == "PROPIETARIO"


# ======================================================================
# Actualizar
# ======================================================================
@pytest.mark.asyncio
async def test_actualizar_proyecto(client: AsyncClient, auth_headers: dict):
    r_crear = await client.post(
        "/api/v1/proyectos",
        headers=auth_headers,
        json={"nombre": "Original"},
    )
    proyecto_id = r_crear.json()["id"]

    r = await client.put(
        f"/api/v1/proyectos/{proyecto_id}",
        headers=auth_headers,
        json={"nombre": "Actualizado", "descripcion": "Nueva desc"},
    )
    assert r.status_code == 200
    assert r.json()["nombre"] == "Actualizado"
    assert r.json()["descripcion"] == "Nueva desc"


# ======================================================================
# Archivar / reactivar
# ======================================================================
@pytest.mark.asyncio
async def test_archivar_y_reactivar(client: AsyncClient, auth_headers: dict):
    r_crear = await client.post(
        "/api/v1/proyectos",
        headers=auth_headers,
        json={"nombre": "Para archivar"},
    )
    proyecto_id = r_crear.json()["id"]

    r1 = await client.post(
        f"/api/v1/proyectos/{proyecto_id}/archivar", headers=auth_headers
    )
    assert r1.status_code == 200
    assert r1.json()["estado"] == "ARCHIVADO"

    r2 = await client.post(
        f"/api/v1/proyectos/{proyecto_id}/reactivar", headers=auth_headers
    )
    assert r2.status_code == 200
    assert r2.json()["estado"] == "ACTIVO"


# ======================================================================
# Miembros
# ======================================================================
@pytest.mark.asyncio
async def test_agregar_miembro(
    client: AsyncClient, auth_headers: dict, usuario_creado: dict
):
    # Crear un segundo usuario
    r_u2 = await client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "María",
            "email": "maria@example.com",
            "password": "password123",
        },
    )
    usuario2_id = r_u2.json()["id"]

    # Crear proyecto con el primer usuario
    r_proy = await client.post(
        "/api/v1/proyectos",
        headers=auth_headers,
        json={"nombre": "Con equipo"},
    )
    proyecto_id = r_proy.json()["id"]

    # Agregar a María como EDITOR
    r = await client.post(
        f"/api/v1/proyectos/{proyecto_id}/miembros",
        headers=auth_headers,
        json={"id_usuario": usuario2_id, "rol_en_proyecto": "EDITOR"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["rol_en_proyecto"] == "EDITOR"


@pytest.mark.asyncio
async def test_agregar_miembro_duplicado(
    client: AsyncClient, auth_headers: dict
):
    r_u2 = await client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "Pedro",
            "email": "pedro@example.com",
            "password": "password123",
        },
    )
    usuario2_id = r_u2.json()["id"]

    r_proy = await client.post(
        "/api/v1/proyectos",
        headers=auth_headers,
        json={"nombre": "Dup test"},
    )
    proyecto_id = r_proy.json()["id"]

    # Primer intento OK
    r1 = await client.post(
        f"/api/v1/proyectos/{proyecto_id}/miembros",
        headers=auth_headers,
        json={"id_usuario": usuario2_id, "rol_en_proyecto": "EDITOR"},
    )
    assert r1.status_code == 201

    # Segundo intento → conflicto
    r2 = await client.post(
        f"/api/v1/proyectos/{proyecto_id}/miembros",
        headers=auth_headers,
        json={"id_usuario": usuario2_id, "rol_en_proyecto": "LECTOR"},
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_no_se_puede_agregar_propietario_por_esta_via(
    client: AsyncClient, auth_headers: dict
):
    r_u2 = await client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "Otro",
            "email": "otro@example.com",
            "password": "password123",
        },
    )
    usuario2_id = r_u2.json()["id"]

    r_proy = await client.post(
        "/api/v1/proyectos",
        headers=auth_headers,
        json={"nombre": "No doble owner"},
    )
    proyecto_id = r_proy.json()["id"]

    r = await client.post(
        f"/api/v1/proyectos/{proyecto_id}/miembros",
        headers=auth_headers,
        json={"id_usuario": usuario2_id, "rol_en_proyecto": "PROPIETARIO"},
    )
    # El servicio debe rechazarlo (422 por ValidationError)
    assert r.status_code in (400, 422)


# ======================================================================
# Aislamiento: otro usuario no ve mi proyecto
# ======================================================================
@pytest.mark.asyncio
async def test_otro_usuario_no_ve_proyecto(
    client: AsyncClient, auth_headers: dict
):
    # Crear proyecto con el usuario 1
    r_proy = await client.post(
        "/api/v1/proyectos",
        headers=auth_headers,
        json={"nombre": "Privado"},
    )
    proyecto_id = r_proy.json()["id"]

    # Registro y login del usuario 2
    await client.post(
        "/api/v1/auth/registro",
        json={
            "nombre_completo": "Intruso",
            "email": "intruso@example.com",
            "password": "password123",
        },
    )
    r_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "intruso@example.com", "password": "password123"},
    )
    token2 = r_login.json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    # Usuario 2 intenta acceder al proyecto de usuario 1
    r = await client.get(f"/api/v1/proyectos/{proyecto_id}", headers=headers2)
    assert r.status_code == 404


# ======================================================================
# Eliminar
# ======================================================================
@pytest.mark.asyncio
async def test_eliminar_proyecto(client: AsyncClient, auth_headers: dict):
    r_crear = await client.post(
        "/api/v1/proyectos",
        headers=auth_headers,
        json={"nombre": "Para borrar"},
    )
    proyecto_id = r_crear.json()["id"]

    r = await client.delete(
        f"/api/v1/proyectos/{proyecto_id}", headers=auth_headers
    )
    assert r.status_code == 204

    # Ya no existe
    r2 = await client.get(
        f"/api/v1/proyectos/{proyecto_id}", headers=auth_headers
    )
    assert r2.status_code == 404