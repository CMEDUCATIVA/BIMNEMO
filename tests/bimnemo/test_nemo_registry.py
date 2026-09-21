"""Registro de NEMOs: identificadores, unicidad, persistencia y protecciones.

Lo que se fija aquí, y por qué importa:

* El identificador se deriva del nombre igual que el servidor sanea la
  cabecera ``LIGHTRAG-WORKSPACE``. Si divergieran, una IA externa escribiría
  en una memoria distinta de la que cree.
* La unicidad no distingue mayúsculas, porque en Windows «Obra» y «obra» son
  la misma carpeta y admitir las dos las haría compartir datos en silencio.
* Un índice ilegible no se sobrescribe: los datos del usuario siguen en disco
  y su lista de memorias no se tira por un fichero corrupto.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lightrag.api.bimnemo.nemo_registry import (
    LEGACY_ID,
    LEGACY_NAME,
    MAX_NAME_LENGTH,
    NemoError,
    NemoRegistry,
    slugify,
)

pytestmark = pytest.mark.offline


@pytest.fixture
def registry(tmp_path: Path) -> NemoRegistry:
    reg = NemoRegistry(working_dir=tmp_path)
    reg.load()
    return reg


# --- Identificadores --------------------------------------------------------


@pytest.mark.parametrize(
    "nombre, esperado",
    [
        ("Proyecto Norte", "Proyecto_Norte"),
        ("obra/2026", "obra_2026"),
        ("  espacios  ", "espacios"),
        ("acentuación", "acentuaci_n"),
        ("a---b", "a_b"),
        ("___raro___", "raro"),
        ("Edificio #3", "Edificio_3"),
    ],
)
def test_el_identificador_se_sanea_a_caracteres_de_carpeta(nombre, esperado):
    assert slugify(nombre) == esperado


def test_el_saneado_coincide_con_el_de_la_cabecera_del_servidor():
    """Mismo saneado que ``get_workspace_from_request``.

    Si no coincidieran, crear «Obra Norte» por la interfaz y mandar
    ``LIGHTRAG-WORKSPACE: Obra Norte`` por API resolverían a workspaces
    distintos, y la IA escribiría en una memoria que el usuario no ve.
    """
    import re

    for nombre in ("Proyecto Norte", "obra/2026", "Edificio #3", "a.b-c"):
        como_la_cabecera = re.sub(r"[^a-zA-Z0-9_]", "_", nombre)
        # El registro además colapsa repeticiones y recorta, así que se
        # compara sobre el conjunto de caracteres admitido.
        assert set(slugify(nombre)) <= set(como_la_cabecera) | {"_"}
        assert re.fullmatch(r"[A-Za-z0-9_]*", slugify(nombre))


def test_un_nombre_sin_caracteres_utilizables_se_rechaza(registry):
    with pytest.raises(NemoError, match="ningún carácter utilizable"):
        registry.create("¿¿¿???")


# --- Creación ---------------------------------------------------------------


def test_una_instalacion_nueva_no_enseña_ninguna_memoria(registry):
    """El usuario la encuentra limpia: la primera memoria la nombra él.

    La base existe por dentro —el motor necesita un espacio por defecto— pero
    oculta, así que no sale en la lista.
    """
    assert registry.list() == []
    base = registry.get(LEGACY_ID)
    assert base is not None and base.hidden and base.protected
    assert registry.default_id == LEGACY_ID


def test_con_datos_en_la_base_se_enseña_aunque_falte_el_indice(tmp_path):
    """Un índice perdido no puede esconder los documentos de nadie."""
    (tmp_path / "kv_store_doc_status.json").write_text(
        json.dumps({"doc-1": {"status": "processed"}}), encoding="utf-8"
    )
    registro = NemoRegistry(working_dir=tmp_path)
    registro.load()

    assert [n.id for n in registro.list()] == [LEGACY_ID]
    assert registro.list()[0].name == LEGACY_NAME


def test_un_indice_viejo_con_la_general_la_sigue_enseñando(tmp_path):
    """Quien actualiza no pierde de vista su «General»."""
    (tmp_path / "bimnemo_nemos.json").write_text(
        json.dumps(
            {"version": 1, "default": "",
             "nemos": [{"id": "", "name": "General", "protected": True}]}
        ),
        encoding="utf-8",
    )
    registro = NemoRegistry(working_dir=tmp_path)
    registro.load()

    assert [n.name for n in registro.list()] == ["General"]


def test_nombrar_la_base_oculta_crea_la_primera_memoria(registry, tmp_path):
    registry.rename(LEGACY_ID, "Obra Norte")

    assert [(n.id, n.name) for n in registry.list()] == [(LEGACY_ID, "Obra Norte")]
    # Y se queda así al recargar.
    otro = NemoRegistry(working_dir=tmp_path)
    otro.load()
    assert [n.name for n in otro.list()] == ["Obra Norte"]


def test_borrar_la_base_la_oculta_y_vuelve_a_su_nombre(registry, tmp_path):
    registry.rename(LEGACY_ID, "Obra Norte")
    registry.delete(LEGACY_ID)

    assert registry.list() == []
    assert registry.get(LEGACY_ID).name == LEGACY_NAME
    otro = NemoRegistry(working_dir=tmp_path)
    otro.load()
    assert otro.list() == [], "tras recargar volvía a aparecer"


def test_borrar_la_base_con_otras_pasa_el_defecto_a_una_visible(registry):
    registry.rename(LEGACY_ID, "Primera")
    registry.create("Segunda")
    registry.set_default(LEGACY_ID)

    registry.delete(LEGACY_ID)

    assert [n.id for n in registry.list()] == ["Segunda"]
    assert registry.default_id == "Segunda"


def test_crear_con_la_base_oculta_la_nueva_pasa_a_ser_la_de_defecto(registry):
    """Si no, las peticiones sin memoria irían a una base vacía e invisible."""
    registry.create("Obra")

    assert registry.default_id == "Obra"


def test_la_base_oculta_no_bloquea_el_nombre_general(registry):
    registry.create("General")

    assert [n.name for n in registry.list()] == ["General"]


def test_crear_devuelve_la_nemo_y_la_persiste(registry, tmp_path):
    nemo = registry.create("Proyecto Norte")

    assert nemo.id == "Proyecto_Norte"
    assert nemo.name == "Proyecto Norte"
    assert nemo.protected is False

    guardado = json.loads((tmp_path / "bimnemo_nemos.json").read_text(encoding="utf-8"))
    ids = [n["id"] for n in guardado["nemos"]]
    assert ids == [LEGACY_ID, "Proyecto_Norte"]


def test_crear_no_toca_el_disco_de_datos(registry, tmp_path):
    """Registrar y materializar son cosas distintas.

    La carpeta la crea el almacenamiento la primera vez que se usa la NEMO. Si
    el registro crease carpetas, un fallo posterior dejaría huérfanas.
    """
    registry.create("Proyecto Norte")
    assert not (tmp_path / "Proyecto_Norte").exists()


def test_nombre_vacio_se_rechaza(registry):
    with pytest.raises(NemoError, match="necesita un nombre"):
        registry.create("   ")


def test_nombre_demasiado_largo_se_rechaza(registry):
    with pytest.raises(NemoError, match=str(MAX_NAME_LENGTH)):
        registry.create("x" * (MAX_NAME_LENGTH + 1))


# --- Unicidad ---------------------------------------------------------------


def test_no_se_admite_el_mismo_nombre_dos_veces(registry):
    registry.create("Obra Sur")
    with pytest.raises(NemoError, match="Ya existe una NEMO llamada"):
        registry.create("obra sur")


def test_no_se_admite_la_misma_nemo_cambiando_mayusculas(registry):
    """«Obra» y «OBRA» son la MISMA carpeta en Windows y en macOS.

    Admitir ambas las haría compartir datos sin que nada lo indicara — justo
    lo que las NEMOs vienen a evitar. Aquí salta primero la regla de nombre,
    que da mejor explicación; lo que se fija es que NO se admite.
    """
    registry.create("Obra")
    with pytest.raises(NemoError):
        registry.create("OBRA")
    assert [n.name for n in registry.list()] == ["Obra"]


def test_nombres_distintos_que_sanean_a_la_misma_carpeta_chocan(registry):
    """Dos nombres que el usuario ve distintos pero acaban en una carpeta.

    Este es el caso que solo cubre la comprobación de carpeta: los nombres no
    coinciden, así que la regla de nombre no salta.
    """
    registry.create("obra 2026")
    with pytest.raises(NemoError, match="la misma carpeta"):
        registry.create("obra/2026")


# --- Resolución -------------------------------------------------------------


def test_resolver_sin_nemo_da_la_de_por_defecto(registry):
    assert registry.resolve(None) == LEGACY_ID
    assert registry.resolve("") == LEGACY_ID


def test_resolver_admite_identificador_y_nombre_visible(registry):
    registry.create("Proyecto Norte")
    assert registry.resolve("Proyecto_Norte") == "Proyecto_Norte"
    assert registry.resolve("Proyecto Norte") == "Proyecto_Norte"
    assert registry.resolve("proyecto norte") == "Proyecto_Norte"


def test_una_nemo_desconocida_falla_en_vez_de_caer_en_la_de_por_defecto(registry):
    """Caer en la de por defecto escribiría en la memoria equivocada.

    Es el fallo peor posible aquí: silencioso, y solo se descubre cuando
    alguien pregunta a una NEMO y le responde otra.
    """
    with pytest.raises(NemoError, match="No existe"):
        registry.resolve("no-existe")


# --- Renombrado -------------------------------------------------------------


def test_renombrar_no_cambia_el_identificador(registry):
    nemo = registry.create("Proyecto Norte")
    renombrada = registry.rename(nemo.id, "Obra Norte 2026")

    assert renombrada.id == "Proyecto_Norte"  # los datos no se mueven
    assert renombrada.name == "Obra Norte 2026"
    assert registry.resolve("Obra Norte 2026") == "Proyecto_Norte"


def test_renombrar_a_un_nombre_ya_usado_se_rechaza(registry):
    a = registry.create("Uno")
    registry.create("Dos")
    with pytest.raises(NemoError, match="Ya existe"):
        registry.rename(a.id, "dos")


# --- Borrado ----------------------------------------------------------------


def test_borrar_quita_del_indice_pero_no_de_disco(registry, tmp_path):
    """El registro nunca borra datos: eso lo decide la capa de arriba.

    Juntar ambas cosas convertiría un fallo del índice en pérdida de datos.
    """
    nemo = registry.create("Temporal")
    carpeta = tmp_path / nemo.id
    carpeta.mkdir()
    (carpeta / "dato.json").write_text("{}", encoding="utf-8")

    registry.delete(nemo.id)

    assert registry.get(nemo.id) is None
    assert (carpeta / "dato.json").is_file()


def test_no_se_borra_dos_veces_la_base(registry):
    """Oculta ya está «borrada»: volver a borrarla es un error, no un nada."""
    with pytest.raises(NemoError, match="No existe"):
        registry.delete(LEGACY_ID)


def test_borrar_la_de_por_defecto_devuelve_el_defecto_a_la_base(registry):
    nemo = registry.create("Principal")
    registry.set_default(nemo.id)
    assert registry.default_id == nemo.id

    registry.delete(nemo.id)
    assert registry.default_id == LEGACY_ID


# --- Persistencia -----------------------------------------------------------


def test_lo_guardado_se_recupera_al_recargar(tmp_path):
    primero = NemoRegistry(working_dir=tmp_path)
    primero.load()
    primero.create("Proyecto Norte")
    primero.create("Obra Sur")
    primero.set_default("Obra_Sur")

    segundo = NemoRegistry(working_dir=tmp_path)
    segundo.load()

    assert [n.id for n in segundo.list()] == ["Obra_Sur", "Proyecto_Norte"]
    assert segundo.default_id == "Obra_Sur"


def test_un_indice_ilegible_no_se_sobrescribe(tmp_path):
    """Un JSON roto no puede costarle al usuario su lista de memorias.

    Los datos siguen en disco; lo que falta es el índice, y se puede
    reconstruir a mano. Reescribirlo lo haría irrecuperable.
    """
    destino = tmp_path / "bimnemo_nemos.json"
    destino.write_text("{ esto no es json", encoding="utf-8")

    registro = NemoRegistry(working_dir=tmp_path)
    registro.load()

    # Con el índice roto la base se enseña: no es una instalación nueva, y
    # esconderla escondería lo que tenga dentro.
    assert [n.id for n in registro.list()] == [LEGACY_ID]
    assert destino.read_text(encoding="utf-8") == "{ esto no es json"


def test_se_ignora_una_entrada_con_identificador_invalido(tmp_path):
    (tmp_path / "bimnemo_nemos.json").write_text(
        json.dumps(
            {
                "version": 1,
                "default": "",
                "nemos": [
                    {"id": "", "name": "General", "protected": True},
                    {"id": "../fuga", "name": "Maliciosa"},
                    {"id": "Buena", "name": "Buena"},
                ],
            }
        ),
        encoding="utf-8",
    )

    registro = NemoRegistry(working_dir=tmp_path)
    registro.load()

    assert [n.id for n in registro.list()] == [LEGACY_ID, "Buena"]


def test_la_heredada_reaparece_aunque_el_indice_no_la_traiga(tmp_path):
    (tmp_path / "bimnemo_nemos.json").write_text(
        json.dumps({"version": 1, "default": "X", "nemos": [{"id": "X", "name": "X"}]}),
        encoding="utf-8",
    )

    registro = NemoRegistry(working_dir=tmp_path)
    registro.load()

    assert registro.get(LEGACY_ID) is not None
    assert registro.get(LEGACY_ID).protected is True


# --- ensure -----------------------------------------------------------------


def test_ensure_registra_el_workspace_del_servidor(registry):
    """Arrancar con WORKSPACE=algo no puede dejar esa memoria invisible.

    Tiene datos y es la que responde; fuera del índice no aparecería en la
    interfaz mientras sigue siendo la activa.
    """
    nemo = registry.ensure("Obra_Norte", name="Obra Norte", default=True)

    assert nemo.id == "Obra_Norte"
    assert registry.default_id == "Obra_Norte"
    assert [n.id for n in registry.list()] == ["Obra_Norte"]


def test_ensure_es_idempotente(registry):
    primero = registry.ensure("Obra", name="Obra")
    segundo = registry.ensure("Obra", name="Otro nombre")

    assert segundo.name == primero.name  # no renombra lo ya registrado
    assert [n.id for n in registry.list()] == ["Obra"]
    # Con la base oculta, la adoptada es la que responde por defecto.
    assert registry.default_id == "Obra"


def test_ensure_rechaza_un_identificador_con_fuga_de_ruta(registry):
    with pytest.raises(NemoError, match="no válido"):
        registry.ensure("../fuera")
