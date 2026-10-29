from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import date, datetime
from typing import Optional, List, Any
import unicodedata
from app.modules.clients.schemas import ClientResponse
from app.modules.catalogos.schemas import MonedaResponse
from app.modules.productos.schemas import MaterialResponse

class ClienteRapidoCreate(BaseModel):
    """Alta de cliente desde el flujo de cotización con el mismo perfil
    completo que el módulo Clientes. Si el teléfono ya existe se devuelve
    ESE en vez de duplicar."""

    nombre: str = Field(min_length=1, max_length=150)
    telefono: str = Field(min_length=1, max_length=50)
    cedula: Optional[str] = Field(None, max_length=30)
    direccion: Optional[str] = Field(None, max_length=2000)
    ciudad: Optional[str] = Field(None, max_length=100)
    estado: Optional[str] = Field(None, max_length=100)
    observaciones: Optional[str] = Field(None, max_length=2000)


class ClienteRapidoResponse(BaseModel):
    id: int
    nombre: str
    telefono: str
    cedula: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    estado: Optional[str] = None
    observaciones: Optional[str] = None


TIPOS_ITEM = ("FABRICADO", "REVENTA", "INSUMO", "REPARACION", "SERVICIO")


# ------------------------------------------------------------
# Piezas de un renglón-juego
# ------------------------------------------------------------
MAX_PIEZAS_JUEGO = 50


def clave_pieza(nombre: str) -> str:
    """Clave para comparar nombres sin acentos ni mayúsculas ("Sillón" = "SILLON")."""
    plano = unicodedata.normalize("NFD", (nombre or "").strip().upper())
    return "".join(c for c in plano if unicodedata.category(c) != "Mn")


def validar_piezas_juego(piezas: "list[PiezaJuegoBase]", tipo_item: str) -> None:
    """Reglas compartidas por cotización y pedido.

    Las piezas no llevan precio: son la apertura interna de producción/costos
    de un renglón con precio global. Solo tienen sentido en FABRICADO y sus
    nombres deben ser únicos (sin duplicar por mayúsculas/acentos).
    """
    if not piezas:
        return
    if tipo_item != "FABRICADO":
        raise ValueError("Las piezas del juego solo aplican a renglones FABRICADO.")
    if len(piezas) > MAX_PIEZAS_JUEGO:
        raise ValueError(f"Un renglón no puede tener más de {MAX_PIEZAS_JUEGO} piezas.")
    vistas: set[str] = set()
    for pieza in piezas:
        nombre = (pieza.nombre or "").strip()
        if not nombre:
            raise ValueError("Cada pieza del juego debe tener un nombre.")
        clave = clave_pieza(nombre)
        if clave in vistas:
            raise ValueError(f"La pieza '{nombre}' está repetida en el juego.")
        vistas.add(clave)


class PiezaJuegoBase(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    # Cantidad por UNIDAD del renglón (por juego): 6 sillas por comedor.
    cantidad: float = Field(gt=0, le=1000)
    notas: Optional[str] = None
    # Foto opcional de la pieza como data URL (el navegador la comprime antes
    # de enviarla; el backend solo la guarda con la pieza). No es obligatoria.
    foto: Optional[str] = Field(None, max_length=2_000_000)

    @field_validator("foto")
    @classmethod
    def _validar_foto(cls, valor: Optional[str]) -> Optional[str]:
        if valor is None:
            return None
        valor = valor.strip()
        if not valor:
            return None
        if not valor.startswith("data:image/") or ";base64," not in valor:
            raise ValueError("La foto de la pieza debe ser una imagen válida.")
        if len(valor) > 1_500_000:
            raise ValueError("La foto de la pieza es demasiado grande (máx. 1,5 MB).")
        return valor

    @model_validator(mode="after")
    def _normalizar(self):
        self.nombre = self.nombre.strip()
        self.notas = (self.notas or "").strip() or None
        return self


class PiezaJuegoCreate(PiezaJuegoBase):
    pass


class DetalleCotizacionPiezaResponse(PiezaJuegoBase):
    id: int
    detalle_cotizacion_id: int
    orden: int

    class Config:
        from_attributes = True


class DetalleCotizacionPiezaListaResponse(BaseModel):
    """Pieza para los listados: sin la foto (data URL) para no inflar el JSON."""
    id: int
    detalle_cotizacion_id: int
    nombre: str
    cantidad: float
    notas: Optional[str] = None
    orden: int

    class Config:
        from_attributes = True


class DetalleCotizacionBase(BaseModel):
    producto_id: Optional[int] = None
    material_id: Optional[int] = None
    tipo_item: str = Field("FABRICADO", pattern=r"^(FABRICADO|REVENTA|INSUMO|REPARACION|SERVICIO)$")
    cantidad: float = Field(gt=0)
    precio: float = Field(ge=0)
    # Captura flexible de insumos (madera): la cantidad/precio van en la unidad
    # vendida ('CM' o la base) y `cantidad_base` es la equivalencia en la
    # unidad del inventario. El servicio recalcula `cantidad_base`; se acepta en
    # el payload para que el frontend pueda mostrar la vista previa exacta.
    unidad_captura: Optional[str] = Field(None, pattern=r"^(M|CM)$")
    cantidad_base: Optional[float] = Field(None, gt=0)
    alto: Optional[float] = Field(None, ge=0)
    ancho: Optional[float] = Field(None, ge=0)
    largo: Optional[float] = Field(None, ge=0)
    descripcion_especifica: Optional[str] = None
    observaciones: Optional[str] = None
    es_obsequio: bool = False
    costo_materiales: Optional[float] = Field(None, ge=0)
    costo_mano_obra: Optional[float] = Field(None, ge=0)
    costo_gastos: Optional[float] = Field(None, ge=0)
    costo_total: Optional[float] = Field(None, ge=0)
    receta_personalizada: Optional[Any] = None

class DetalleCotizacionCreate(DetalleCotizacionBase):
    # Piezas del juego (opcional). Si vienen, al convertir se crea una orden de
    # producción por pieza; el renglón conserva su precio global. None = no se
    # enviaron (no confundir con [] explícito: "este renglón no es un juego").
    piezas: Optional[List[PiezaJuegoCreate]] = None

    @model_validator(mode="after")
    def _validate_item(self):
        validar_piezas_juego(self.piezas or [], self.tipo_item)
        # La validación de integridad vive SOLO en el Create: el Response
        # también debe poder serializar cotizaciones 100% personalizadas
        # (producto_id NULL, p. ej. guardadas desde el Cotizador IA sin
        # producto base), que la BD sí permite.
        if self.tipo_item == "INSUMO":
            if not self.material_id:
                raise ValueError("material_id es requerido para tipo_item INSUMO")
            if self.producto_id:
                raise ValueError("producto_id no debe enviarse para tipo_item INSUMO")
        elif self.tipo_item in ("REPARACION", "SERVICIO"):
            if self.producto_id:
                raise ValueError("producto_id no debe enviarse para tipo_item REPARACION/SERVICIO")
            if self.material_id:
                raise ValueError("material_id no debe enviarse para tipo_item REPARACION/SERVICIO")
            if not (self.descripcion_especifica or self.observaciones):
                raise ValueError("La descripción es obligatoria para tipo_item REPARACION/SERVICIO")
        elif self.tipo_item == "FABRICADO":
            # Mueble a la medida: sin producto de catálogo, descrito en
            # descripcion_especifica (p. ej. "JUEGO DE SALA: sofá 3 puestos +
            # 2 poltronas"). El precio es manual (no hay receta que costear).
            if not self.producto_id and not (self.descripcion_especifica or self.observaciones):
                raise ValueError(
                    "producto_id es requerido para tipo_item FABRICADO "
                    "(o describe el mueble a medida en descripcion_especifica)"
                )
        else:
            if not self.producto_id:
                raise ValueError("producto_id es requerido para tipo_item REVENTA")
        return self

class DetalleCotizacionResponse(DetalleCotizacionBase):
    id: int
    cotizacion_id: int
    material: Optional[MaterialResponse] = None
    piezas: List[DetalleCotizacionPiezaResponse] = []

    class Config:
        from_attributes = True


class DetalleCotizacionListaResponse(DetalleCotizacionBase):
    """Renglón de los listados: piezas sin foto (solo nombre/cantidad/nota)."""
    id: int
    cotizacion_id: int
    material: Optional[MaterialResponse] = None
    piezas: List[DetalleCotizacionPiezaListaResponse] = []

    class Config:
        from_attributes = True

class CotizacionBase(BaseModel):
    fecha: date
    estado: str
    total_estimado: float = Field(ge=0)
    moneda_id: int = 1
    tasa_cambio: float = Field(1.0, gt=0)
    total_en_moneda_base: Optional[float] = Field(None, ge=0)
    observaciones: Optional[str] = None

class CotizacionCreate(CotizacionBase):
    cliente_id: int
    # Fecha opcional: si no se envía (o viene null), el servicio guarda HOY en
    # hora Venezuela (`hoy_ve`). El formulario la manda siempre; esto protege a
    # scripts, modo offline y clientes viejos de crear cotizaciones sin fecha.
    fecha: Optional[date] = None
    detalles: List[DetalleCotizacionCreate] = []

class CotizacionUpdate(BaseModel):
    cliente_id: Optional[int] = None
    fecha: Optional[date] = None
    estado: Optional[str] = None
    total_estimado: Optional[float] = Field(None, ge=0)
    moneda_id: Optional[int] = None
    tasa_cambio: Optional[float] = Field(None, gt=0)
    total_en_moneda_base: Optional[float] = Field(None, ge=0)
    observaciones: Optional[str] = None
    # Reemplazo COMPLETO de los renglones (mismo contrato que al crear): si se
    # envía, la cotización queda exactamente con estos detalles.
    detalles: Optional[List[DetalleCotizacionCreate]] = None

class CotizacionResponse(CotizacionBase):
    id: int
    cliente_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    creado_por_id: Optional[int] = None
    actualizado_por_id: Optional[int] = None
    creador_nombre: Optional[str] = None
    cliente: Optional[ClientResponse] = None
    moneda: Optional[MonedaResponse] = None
    detalles: List[DetalleCotizacionResponse] = []
    # Atributos anotados por el servicio (no son columnas): si la cotización ya
    # fue convertida a pedido, aquí viene el id/estado del pedido para que la UI
    # la distinga y no ofrezca convertirla otra vez.
    pedido_id: Optional[int] = None
    pedido_estado: Optional[str] = None

    class Config:
        from_attributes = True


class CotizacionListaResponse(CotizacionResponse):
    """Listado: mismo contrato que el detalle pero sin las fotos de las piezas."""
    detalles: List[DetalleCotizacionListaResponse] = []
