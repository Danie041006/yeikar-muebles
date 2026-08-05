--
-- PostgreSQL database dump
--

\restrict MzzuR5HfkLog6V9oRO4NVKzCErxLwr7jUpdgwmawLshHUmVakNu0TxblxiTpRox

-- Dumped from database version 17.10 (Debian 17.10-0+deb13u1)
-- Dumped by pg_dump version 17.10 (Debian 17.10-0+deb13u1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: postgres
--

-- *not* creating schema, since initdb creates it


ALTER SCHEMA public OWNER TO postgres;

--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: postgres
--

COMMENT ON SCHEMA public IS '';


--
-- Name: set_updated_at(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.set_updated_at() OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: area; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.area (
    id bigint NOT NULL,
    nombre character varying(100) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.area OWNER TO postgres;

--
-- Name: TABLE area; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.area IS 'Áreas físicas o lógicas de producción.';


--
-- Name: area_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.area_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.area_id_seq OWNER TO postgres;

--
-- Name: area_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.area_id_seq OWNED BY public.area.id;


--
-- Name: cargo; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cargo (
    id bigint NOT NULL,
    nombre character varying(100) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.cargo OWNER TO postgres;

--
-- Name: TABLE cargo; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.cargo IS 'Cargos ocupados por los empleados.';


--
-- Name: cargo_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.cargo_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.cargo_id_seq OWNER TO postgres;

--
-- Name: cargo_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.cargo_id_seq OWNED BY public.cargo.id;


--
-- Name: cliente; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cliente (
    id bigint NOT NULL,
    nombre character varying(150) NOT NULL,
    telefono character varying(50),
    direccion text,
    email character varying(120),
    ciudad character varying(100),
    estado character varying(100),
    observaciones text,
    fecha_registro date DEFAULT CURRENT_DATE,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.cliente OWNER TO postgres;

--
-- Name: TABLE cliente; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.cliente IS 'Registro de clientes.';


--
-- Name: cliente_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.cliente_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.cliente_id_seq OWNER TO postgres;

--
-- Name: cliente_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.cliente_id_seq OWNED BY public.cliente.id;


--
-- Name: compra; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.compra (
    id bigint NOT NULL,
    proveedor_id bigint NOT NULL,
    moneda_id bigint NOT NULL,
    fecha date NOT NULL,
    estado character varying(50) NOT NULL,
    observaciones text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT compra_estado_check CHECK (((estado)::text = ANY ((ARRAY['BORRADOR'::character varying, 'EMITIDA'::character varying, 'RECIBIDA'::character varying, 'CANCELADA'::character varying])::text[])))
);


ALTER TABLE public.compra OWNER TO postgres;

--
-- Name: TABLE compra; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.compra IS 'Abastecimiento con proveedores.';


--
-- Name: compra_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.compra_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.compra_id_seq OWNER TO postgres;

--
-- Name: compra_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.compra_id_seq OWNED BY public.compra.id;


--
-- Name: consumo_material; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.consumo_material (
    id bigint NOT NULL,
    etapa_produccion_id bigint NOT NULL,
    material_id bigint NOT NULL,
    cantidad numeric(12,2) NOT NULL,
    fecha timestamp without time zone NOT NULL,
    observaciones text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT consumo_material_cantidad_check CHECK ((cantidad > (0)::numeric))
);


ALTER TABLE public.consumo_material OWNER TO postgres;

--
-- Name: TABLE consumo_material; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.consumo_material IS 'Descarga de materiales vinculados a una etapa.';


--
-- Name: consumo_material_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.consumo_material_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.consumo_material_id_seq OWNER TO postgres;

--
-- Name: consumo_material_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.consumo_material_id_seq OWNED BY public.consumo_material.id;


--
-- Name: costo_produccion; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.costo_produccion (
    id bigint NOT NULL,
    orden_produccion_id bigint NOT NULL,
    costo_material numeric(15,2) DEFAULT 0 NOT NULL,
    costo_mano_obra numeric(15,2) DEFAULT 0 NOT NULL,
    costo_gastos numeric(15,2) DEFAULT 0 NOT NULL,
    precio_impuestos_base numeric(15,2) DEFAULT 0 NOT NULL,
    ganancia_porcentaje numeric(5,2) DEFAULT 0 NOT NULL,
    precio_venta_calculado numeric(15,2) DEFAULT 0 NOT NULL,
    costo_total numeric(15,2) DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT costo_produccion_ganancia_porcentaje_check CHECK (((ganancia_porcentaje >= (0)::numeric) AND (ganancia_porcentaje <= (100)::numeric)))
);


ALTER TABLE public.costo_produccion OWNER TO postgres;

--
-- Name: TABLE costo_produccion; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.costo_produccion IS 'Consolidado financiero del costo de manufactura.';


--
-- Name: costo_produccion_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.costo_produccion_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.costo_produccion_id_seq OWNER TO postgres;

--
-- Name: costo_produccion_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.costo_produccion_id_seq OWNED BY public.costo_produccion.id;


--
-- Name: cotizacion; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cotizacion (
    id bigint NOT NULL,
    cliente_id bigint NOT NULL,
    fecha date NOT NULL,
    estado character varying(50) NOT NULL,
    total_estimado numeric(15,2) DEFAULT 0 NOT NULL,
    observaciones text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT cotizacion_estado_check CHECK (((estado)::text = ANY ((ARRAY['BORRADOR'::character varying, 'ENVIADA'::character varying, 'APROBADA'::character varying, 'RECHAZADA'::character varying, 'VENCIDA'::character varying])::text[]))),
    CONSTRAINT cotizacion_total_estimado_check CHECK ((total_estimado >= (0)::numeric))
);


ALTER TABLE public.cotizacion OWNER TO postgres;

--
-- Name: TABLE cotizacion; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.cotizacion IS 'Propuesta económica entregada al cliente.';


--
-- Name: cotizacion_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.cotizacion_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.cotizacion_id_seq OWNER TO postgres;

--
-- Name: cotizacion_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.cotizacion_id_seq OWNED BY public.cotizacion.id;


--
-- Name: detalle_compra; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.detalle_compra (
    id bigint NOT NULL,
    compra_id bigint NOT NULL,
    material_id bigint NOT NULL,
    cantidad numeric(12,2) NOT NULL,
    costo_unitario numeric(15,2) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT detalle_compra_cantidad_check CHECK ((cantidad > (0)::numeric)),
    CONSTRAINT detalle_compra_costo_unitario_check CHECK ((costo_unitario >= (0)::numeric))
);


ALTER TABLE public.detalle_compra OWNER TO postgres;

--
-- Name: TABLE detalle_compra; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.detalle_compra IS 'Renglones de materiales adquiridos.';


--
-- Name: detalle_compra_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.detalle_compra_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.detalle_compra_id_seq OWNER TO postgres;

--
-- Name: detalle_compra_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.detalle_compra_id_seq OWNED BY public.detalle_compra.id;


--
-- Name: detalle_pedido; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.detalle_pedido (
    id bigint NOT NULL,
    pedido_id bigint NOT NULL,
    producto_id bigint NOT NULL,
    cantidad numeric(10,2) NOT NULL,
    precio numeric(15,2) NOT NULL,
    alto numeric(10,2),
    ancho numeric(10,2),
    largo numeric(10,2),
    color character varying(100),
    acabado character varying(100),
    descripcion_especifica text,
    observaciones text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT detalle_pedido_cantidad_check CHECK ((cantidad > (0)::numeric)),
    CONSTRAINT detalle_pedido_precio_check CHECK ((precio >= (0)::numeric))
);


ALTER TABLE public.detalle_pedido OWNER TO postgres;

--
-- Name: TABLE detalle_pedido; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.detalle_pedido IS 'Renglones del pedido con configuración personalizada.';


--
-- Name: detalle_pedido_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.detalle_pedido_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.detalle_pedido_id_seq OWNER TO postgres;

--
-- Name: detalle_pedido_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.detalle_pedido_id_seq OWNED BY public.detalle_pedido.id;


--
-- Name: detalle_venta; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.detalle_venta (
    id bigint NOT NULL,
    venta_id bigint NOT NULL,
    producto_id bigint NOT NULL,
    cantidad numeric(10,2) NOT NULL,
    precio numeric(15,2) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT detalle_venta_cantidad_check CHECK ((cantidad > (0)::numeric)),
    CONSTRAINT detalle_venta_precio_check CHECK ((precio >= (0)::numeric))
);


ALTER TABLE public.detalle_venta OWNER TO postgres;

--
-- Name: TABLE detalle_venta; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.detalle_venta IS 'Líneas de los productos en la venta.';


--
-- Name: detalle_venta_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.detalle_venta_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.detalle_venta_id_seq OWNER TO postgres;

--
-- Name: detalle_venta_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.detalle_venta_id_seq OWNED BY public.detalle_venta.id;


--
-- Name: empleado; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.empleado (
    id bigint NOT NULL,
    nombre character varying(150) NOT NULL,
    cargo_id bigint NOT NULL,
    telefono character varying(50),
    activo boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.empleado OWNER TO postgres;

--
-- Name: TABLE empleado; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.empleado IS 'Personal de la empresa.';


--
-- Name: empleado_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.empleado_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.empleado_id_seq OWNER TO postgres;

--
-- Name: empleado_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.empleado_id_seq OWNED BY public.empleado.id;


--
-- Name: etapa_produccion; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.etapa_produccion (
    id bigint NOT NULL,
    orden_produccion_id bigint NOT NULL,
    area_id bigint NOT NULL,
    empleado_responsable_id bigint NOT NULL,
    fecha_inicio timestamp without time zone,
    fecha_fin timestamp without time zone,
    estado character varying(50) NOT NULL,
    observaciones text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT etapa_produccion_estado_check CHECK (((estado)::text = ANY ((ARRAY['ASIGNADA'::character varying, 'EN_PROCESO'::character varying, 'PAUSADA'::character varying, 'COMPLETADA'::character varying])::text[])))
);


ALTER TABLE public.etapa_produccion OWNER TO postgres;

--
-- Name: TABLE etapa_produccion; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.etapa_produccion IS 'Seguimiento por áreas y encargados de producción.';


--
-- Name: etapa_produccion_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.etapa_produccion_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.etapa_produccion_id_seq OWNER TO postgres;

--
-- Name: etapa_produccion_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.etapa_produccion_id_seq OWNED BY public.etapa_produccion.id;


--
-- Name: gasto; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.gasto (
    id bigint NOT NULL,
    tipo_gasto_id bigint NOT NULL,
    moneda_id bigint NOT NULL,
    fecha date NOT NULL,
    descripcion text,
    monto numeric(15,2) NOT NULL,
    observaciones text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT gasto_monto_check CHECK ((monto > (0)::numeric))
);


ALTER TABLE public.gasto OWNER TO postgres;

--
-- Name: TABLE gasto; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.gasto IS 'Registro de egresos operativos.';


--
-- Name: gasto_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.gasto_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.gasto_id_seq OWNER TO postgres;

--
-- Name: gasto_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.gasto_id_seq OWNED BY public.gasto.id;


--
-- Name: inventario; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.inventario (
    id bigint NOT NULL,
    material_id bigint NOT NULL,
    ubicacion_id bigint NOT NULL,
    cantidad numeric(12,2) DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT inventario_cantidad_check CHECK ((cantidad >= (0)::numeric))
);


ALTER TABLE public.inventario OWNER TO postgres;

--
-- Name: TABLE inventario; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.inventario IS 'Existencias actuales por ubicación.';


--
-- Name: inventario_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.inventario_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.inventario_id_seq OWNER TO postgres;

--
-- Name: inventario_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.inventario_id_seq OWNED BY public.inventario.id;


--
-- Name: mano_obra; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.mano_obra (
    id bigint NOT NULL,
    etapa_produccion_id bigint NOT NULL,
    empleado_id bigint NOT NULL,
    monto numeric(15,2) NOT NULL,
    porcentaje_recargo numeric(5,2) DEFAULT 0 NOT NULL,
    observaciones text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT mano_obra_monto_check CHECK ((monto >= (0)::numeric)),
    CONSTRAINT mano_obra_porcentaje_recargo_check CHECK (((porcentaje_recargo >= (0)::numeric) AND (porcentaje_recargo <= (100)::numeric)))
);


ALTER TABLE public.mano_obra OWNER TO postgres;

--
-- Name: TABLE mano_obra; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.mano_obra IS 'Costos directos por labor de un empleado.';


--
-- Name: mano_obra_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.mano_obra_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.mano_obra_id_seq OWNER TO postgres;

--
-- Name: mano_obra_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.mano_obra_id_seq OWNED BY public.mano_obra.id;


--
-- Name: material; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.material (
    id bigint NOT NULL,
    nombre character varying(150) NOT NULL,
    unidad_medida_id bigint NOT NULL,
    costo_base numeric(15,2) NOT NULL,
    activo boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT material_costo_base_check CHECK ((costo_base >= (0)::numeric))
);


ALTER TABLE public.material OWNER TO postgres;

--
-- Name: TABLE material; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.material IS 'Materia prima e insumos.';


--
-- Name: material_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.material_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.material_id_seq OWNER TO postgres;

--
-- Name: material_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.material_id_seq OWNED BY public.material.id;


--
-- Name: moneda; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.moneda (
    id bigint NOT NULL,
    codigo character varying(3) NOT NULL,
    nombre character varying(50) NOT NULL,
    simbolo character varying(5) NOT NULL,
    activo boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.moneda OWNER TO postgres;

--
-- Name: TABLE moneda; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.moneda IS 'Catálogo de monedas (COP, USD, VES).';


--
-- Name: moneda_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.moneda_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.moneda_id_seq OWNER TO postgres;

--
-- Name: moneda_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.moneda_id_seq OWNED BY public.moneda.id;


--
-- Name: movimiento_inventario; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.movimiento_inventario (
    id bigint NOT NULL,
    material_id bigint NOT NULL,
    ubicacion_id bigint NOT NULL,
    tipo character varying(50) NOT NULL,
    cantidad numeric(12,2) NOT NULL,
    fecha timestamp without time zone NOT NULL,
    referencia_tipo character varying(100),
    referencia_id bigint,
    observaciones text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT movimiento_inventario_cantidad_check CHECK ((cantidad > (0)::numeric)),
    CONSTRAINT movimiento_inventario_tipo_check CHECK (((tipo)::text = ANY ((ARRAY['ENTRADA'::character varying, 'SALIDA'::character varying, 'AJUSTE'::character varying, 'DANO'::character varying, 'DEVOLUCION'::character varying])::text[])))
);


ALTER TABLE public.movimiento_inventario OWNER TO postgres;

--
-- Name: TABLE movimiento_inventario; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.movimiento_inventario IS 'Kardex/Historial de entradas y salidas.';


--
-- Name: movimiento_inventario_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.movimiento_inventario_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.movimiento_inventario_id_seq OWNER TO postgres;

--
-- Name: movimiento_inventario_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.movimiento_inventario_id_seq OWNED BY public.movimiento_inventario.id;


--
-- Name: orden_produccion; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.orden_produccion (
    id bigint NOT NULL,
    detalle_pedido_id bigint NOT NULL,
    fecha_inicio date,
    fecha_fin date,
    estado character varying(50) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT orden_produccion_estado_check CHECK (((estado)::text = ANY ((ARRAY['PENDIENTE'::character varying, 'EN_PRODUCCION'::character varying, 'PAUSADA'::character varying, 'FINALIZADA'::character varying, 'CANCELADA'::character varying])::text[])))
);


ALTER TABLE public.orden_produccion OWNER TO postgres;

--
-- Name: TABLE orden_produccion; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.orden_produccion IS 'Orden fabricada por detalle específico de pedido.';


--
-- Name: orden_produccion_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.orden_produccion_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.orden_produccion_id_seq OWNER TO postgres;

--
-- Name: orden_produccion_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.orden_produccion_id_seq OWNED BY public.orden_produccion.id;


--
-- Name: pago; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.pago (
    id bigint NOT NULL,
    venta_id bigint NOT NULL,
    moneda_id bigint NOT NULL,
    fecha timestamp without time zone NOT NULL,
    monto numeric(15,2) NOT NULL,
    metodo_pago character varying(50) NOT NULL,
    referencia character varying(150),
    observaciones text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pago_metodo_pago_check CHECK (((metodo_pago)::text = ANY ((ARRAY['EFECTIVO_COP'::character varying, 'EFECTIVO_USD'::character varying, 'EFECTIVO_VES'::character varying, 'BANCOLOMBIA'::character varying, 'BANCARIBE'::character varying, 'ZELLE'::character varying])::text[]))),
    CONSTRAINT pago_monto_check CHECK ((monto > (0)::numeric))
);


ALTER TABLE public.pago OWNER TO postgres;

--
-- Name: TABLE pago; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.pago IS 'Abonos y pagos de ventas.';


--
-- Name: pago_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.pago_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.pago_id_seq OWNER TO postgres;

--
-- Name: pago_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.pago_id_seq OWNED BY public.pago.id;


--
-- Name: pedido; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.pedido (
    id bigint NOT NULL,
    cotizacion_id bigint NOT NULL,
    cliente_id bigint NOT NULL,
    fecha date NOT NULL,
    estado character varying(50) NOT NULL,
    observaciones text,
    fecha_entrega_estimada date,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pedido_estado_check CHECK (((estado)::text = ANY ((ARRAY['COTIZADO'::character varying, 'APROBADO'::character varying, 'PRODUCCION'::character varying, 'PAUSADO'::character varying, 'TERMINADO'::character varying, 'ENTREGADO'::character varying, 'CANCELADO'::character varying])::text[])))
);


ALTER TABLE public.pedido OWNER TO postgres;

--
-- Name: TABLE pedido; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.pedido IS 'Solicitud en firme aceptada por el cliente.';


--
-- Name: pedido_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.pedido_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.pedido_id_seq OWNER TO postgres;

--
-- Name: pedido_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.pedido_id_seq OWNED BY public.pedido.id;


--
-- Name: producto; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.producto (
    id bigint NOT NULL,
    nombre character varying(150) NOT NULL,
    codigo character varying(50),
    tipo_producto_id bigint NOT NULL,
    descripcion text,
    activo boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.producto OWNER TO postgres;

--
-- Name: TABLE producto; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.producto IS 'Catálogo de artículos base.';


--
-- Name: producto_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.producto_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.producto_id_seq OWNER TO postgres;

--
-- Name: producto_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.producto_id_seq OWNED BY public.producto.id;


--
-- Name: proveedor; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.proveedor (
    id bigint NOT NULL,
    nombre character varying(150) NOT NULL,
    telefono character varying(50),
    email character varying(150),
    direccion text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.proveedor OWNER TO postgres;

--
-- Name: TABLE proveedor; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.proveedor IS 'Entidades que proveen materiales.';


--
-- Name: proveedor_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.proveedor_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.proveedor_id_seq OWNER TO postgres;

--
-- Name: proveedor_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.proveedor_id_seq OWNED BY public.proveedor.id;


--
-- Name: rol; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.rol (
    id bigint NOT NULL,
    nombre character varying(100) NOT NULL,
    descripcion text,
    activo boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.rol OWNER TO postgres;

--
-- Name: TABLE rol; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.rol IS 'Roles del sistema para control de acceso.';


--
-- Name: rol_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.rol_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.rol_id_seq OWNER TO postgres;

--
-- Name: rol_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.rol_id_seq OWNED BY public.rol.id;


--
-- Name: tasa_cambio; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.tasa_cambio (
    id bigint NOT NULL,
    moneda_origen_id bigint NOT NULL,
    moneda_destino_id bigint NOT NULL,
    valor numeric(15,6) NOT NULL,
    fecha date NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT tasa_cambio_valor_check CHECK ((valor > (0)::numeric))
);


ALTER TABLE public.tasa_cambio OWNER TO postgres;

--
-- Name: TABLE tasa_cambio; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.tasa_cambio IS 'Histórico de tasas de conversión.';


--
-- Name: tasa_cambio_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.tasa_cambio_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.tasa_cambio_id_seq OWNER TO postgres;

--
-- Name: tasa_cambio_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.tasa_cambio_id_seq OWNED BY public.tasa_cambio.id;


--
-- Name: tipo_gasto; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.tipo_gasto (
    id bigint NOT NULL,
    nombre character varying(100) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.tipo_gasto OWNER TO postgres;

--
-- Name: TABLE tipo_gasto; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.tipo_gasto IS 'Categorización de los gastos operativos.';


--
-- Name: tipo_gasto_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.tipo_gasto_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.tipo_gasto_id_seq OWNER TO postgres;

--
-- Name: tipo_gasto_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.tipo_gasto_id_seq OWNED BY public.tipo_gasto.id;


--
-- Name: tipo_producto; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.tipo_producto (
    id bigint NOT NULL,
    nombre character varying(100) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.tipo_producto OWNER TO postgres;

--
-- Name: TABLE tipo_producto; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.tipo_producto IS 'Clasificación principal de los productos.';


--
-- Name: tipo_producto_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.tipo_producto_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.tipo_producto_id_seq OWNER TO postgres;

--
-- Name: tipo_producto_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.tipo_producto_id_seq OWNED BY public.tipo_producto.id;


--
-- Name: ubicacion; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ubicacion (
    id bigint NOT NULL,
    nombre character varying(100) NOT NULL,
    descripcion text,
    tipo character varying(50) NOT NULL,
    activo boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ubicacion_tipo_check CHECK (((tipo)::text = ANY ((ARRAY['DEPOSITO'::character varying, 'TALLER'::character varying, 'PUNTO_VENTA'::character varying])::text[])))
);


ALTER TABLE public.ubicacion OWNER TO postgres;

--
-- Name: TABLE ubicacion; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.ubicacion IS 'Ubicaciones físicas para almacenar inventario.';


--
-- Name: ubicacion_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.ubicacion_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.ubicacion_id_seq OWNER TO postgres;

--
-- Name: ubicacion_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.ubicacion_id_seq OWNED BY public.ubicacion.id;


--
-- Name: unidad_medida; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.unidad_medida (
    id bigint NOT NULL,
    nombre character varying(50) NOT NULL,
    abreviatura character varying(10) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.unidad_medida OWNER TO postgres;

--
-- Name: TABLE unidad_medida; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.unidad_medida IS 'Unidades de medida para los materiales e insumos.';


--
-- Name: unidad_medida_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.unidad_medida_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.unidad_medida_id_seq OWNER TO postgres;

--
-- Name: unidad_medida_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.unidad_medida_id_seq OWNED BY public.unidad_medida.id;


--
-- Name: usuario; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.usuario (
    id bigint NOT NULL,
    empleado_id bigint,
    nombre_usuario character varying(100) NOT NULL,
    email character varying(150),
    password_hash text NOT NULL,
    activo boolean DEFAULT true NOT NULL,
    ultimo_acceso timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.usuario OWNER TO postgres;

--
-- Name: TABLE usuario; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.usuario IS 'Usuarios que acceden al sistema.';


--
-- Name: usuario_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.usuario_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.usuario_id_seq OWNER TO postgres;

--
-- Name: usuario_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.usuario_id_seq OWNED BY public.usuario.id;


--
-- Name: usuario_rol; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.usuario_rol (
    id bigint NOT NULL,
    usuario_id bigint NOT NULL,
    rol_id bigint NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.usuario_rol OWNER TO postgres;

--
-- Name: TABLE usuario_rol; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.usuario_rol IS 'Relación entre usuarios y roles.';


--
-- Name: usuario_rol_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.usuario_rol_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.usuario_rol_id_seq OWNER TO postgres;

--
-- Name: usuario_rol_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.usuario_rol_id_seq OWNED BY public.usuario_rol.id;


--
-- Name: venta; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.venta (
    id bigint NOT NULL,
    pedido_id bigint NOT NULL,
    cliente_id bigint NOT NULL,
    moneda_id bigint NOT NULL,
    fecha date NOT NULL,
    total numeric(15,2) NOT NULL,
    estado character varying(50) NOT NULL,
    observaciones text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT venta_estado_check CHECK (((estado)::text = ANY ((ARRAY['PENDIENTE'::character varying, 'ABONADA'::character varying, 'PAGADA'::character varying, 'CANCELADA'::character varying])::text[]))),
    CONSTRAINT venta_total_check CHECK ((total >= (0)::numeric))
);


ALTER TABLE public.venta OWNER TO postgres;

--
-- Name: TABLE venta; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.venta IS 'Formalización de la entrega y facturación vinculada a un pedido.';


--
-- Name: venta_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.venta_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.venta_id_seq OWNER TO postgres;

--
-- Name: venta_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.venta_id_seq OWNED BY public.venta.id;


--
-- Name: area id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.area ALTER COLUMN id SET DEFAULT nextval('public.area_id_seq'::regclass);


--
-- Name: cargo id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cargo ALTER COLUMN id SET DEFAULT nextval('public.cargo_id_seq'::regclass);


--
-- Name: cliente id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cliente ALTER COLUMN id SET DEFAULT nextval('public.cliente_id_seq'::regclass);


--
-- Name: compra id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.compra ALTER COLUMN id SET DEFAULT nextval('public.compra_id_seq'::regclass);


--
-- Name: consumo_material id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.consumo_material ALTER COLUMN id SET DEFAULT nextval('public.consumo_material_id_seq'::regclass);


--
-- Name: costo_produccion id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.costo_produccion ALTER COLUMN id SET DEFAULT nextval('public.costo_produccion_id_seq'::regclass);


--
-- Name: cotizacion id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cotizacion ALTER COLUMN id SET DEFAULT nextval('public.cotizacion_id_seq'::regclass);


--
-- Name: detalle_compra id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.detalle_compra ALTER COLUMN id SET DEFAULT nextval('public.detalle_compra_id_seq'::regclass);


--
-- Name: detalle_pedido id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.detalle_pedido ALTER COLUMN id SET DEFAULT nextval('public.detalle_pedido_id_seq'::regclass);


--
-- Name: detalle_venta id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.detalle_venta ALTER COLUMN id SET DEFAULT nextval('public.detalle_venta_id_seq'::regclass);


--
-- Name: empleado id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.empleado ALTER COLUMN id SET DEFAULT nextval('public.empleado_id_seq'::regclass);


--
-- Name: etapa_produccion id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.etapa_produccion ALTER COLUMN id SET DEFAULT nextval('public.etapa_produccion_id_seq'::regclass);


--
-- Name: gasto id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gasto ALTER COLUMN id SET DEFAULT nextval('public.gasto_id_seq'::regclass);


--
-- Name: inventario id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventario ALTER COLUMN id SET DEFAULT nextval('public.inventario_id_seq'::regclass);


--
-- Name: mano_obra id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.mano_obra ALTER COLUMN id SET DEFAULT nextval('public.mano_obra_id_seq'::regclass);


--
-- Name: material id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.material ALTER COLUMN id SET DEFAULT nextval('public.material_id_seq'::regclass);


--
-- Name: moneda id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.moneda ALTER COLUMN id SET DEFAULT nextval('public.moneda_id_seq'::regclass);


--
-- Name: movimiento_inventario id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.movimiento_inventario ALTER COLUMN id SET DEFAULT nextval('public.movimiento_inventario_id_seq'::regclass);


--
-- Name: orden_produccion id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.orden_produccion ALTER COLUMN id SET DEFAULT nextval('public.orden_produccion_id_seq'::regclass);


--
-- Name: pago id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pago ALTER COLUMN id SET DEFAULT nextval('public.pago_id_seq'::regclass);


--
-- Name: pedido id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pedido ALTER COLUMN id SET DEFAULT nextval('public.pedido_id_seq'::regclass);


--
-- Name: producto id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.producto ALTER COLUMN id SET DEFAULT nextval('public.producto_id_seq'::regclass);


--
-- Name: proveedor id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.proveedor ALTER COLUMN id SET DEFAULT nextval('public.proveedor_id_seq'::regclass);


--
-- Name: rol id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rol ALTER COLUMN id SET DEFAULT nextval('public.rol_id_seq'::regclass);


--
-- Name: tasa_cambio id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tasa_cambio ALTER COLUMN id SET DEFAULT nextval('public.tasa_cambio_id_seq'::regclass);


--
-- Name: tipo_gasto id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tipo_gasto ALTER COLUMN id SET DEFAULT nextval('public.tipo_gasto_id_seq'::regclass);


--
-- Name: tipo_producto id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tipo_producto ALTER COLUMN id SET DEFAULT nextval('public.tipo_producto_id_seq'::regclass);


--
-- Name: ubicacion id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ubicacion ALTER COLUMN id SET DEFAULT nextval('public.ubicacion_id_seq'::regclass);


--
-- Name: unidad_medida id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.unidad_medida ALTER COLUMN id SET DEFAULT nextval('public.unidad_medida_id_seq'::regclass);


--
-- Name: usuario id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.usuario ALTER COLUMN id SET DEFAULT nextval('public.usuario_id_seq'::regclass);


--
-- Name: usuario_rol id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.usuario_rol ALTER COLUMN id SET DEFAULT nextval('public.usuario_rol_id_seq'::regclass);


--
-- Name: venta id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.venta ALTER COLUMN id SET DEFAULT nextval('public.venta_id_seq'::regclass);


--
-- Name: area area_nombre_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.area
    ADD CONSTRAINT area_nombre_key UNIQUE (nombre);


--
-- Name: area area_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.area
    ADD CONSTRAINT area_pkey PRIMARY KEY (id);


--
-- Name: cargo cargo_nombre_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cargo
    ADD CONSTRAINT cargo_nombre_key UNIQUE (nombre);


--
-- Name: cargo cargo_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cargo
    ADD CONSTRAINT cargo_pkey PRIMARY KEY (id);


--
-- Name: cliente cliente_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cliente
    ADD CONSTRAINT cliente_pkey PRIMARY KEY (id);


--
-- Name: compra compra_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.compra
    ADD CONSTRAINT compra_pkey PRIMARY KEY (id);


--
-- Name: consumo_material consumo_material_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.consumo_material
    ADD CONSTRAINT consumo_material_pkey PRIMARY KEY (id);


--
-- Name: costo_produccion costo_produccion_orden_produccion_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.costo_produccion
    ADD CONSTRAINT costo_produccion_orden_produccion_id_key UNIQUE (orden_produccion_id);


--
-- Name: costo_produccion costo_produccion_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.costo_produccion
    ADD CONSTRAINT costo_produccion_pkey PRIMARY KEY (id);


--
-- Name: cotizacion cotizacion_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cotizacion
    ADD CONSTRAINT cotizacion_pkey PRIMARY KEY (id);


--
-- Name: detalle_compra detalle_compra_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.detalle_compra
    ADD CONSTRAINT detalle_compra_pkey PRIMARY KEY (id);


--
-- Name: detalle_pedido detalle_pedido_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.detalle_pedido
    ADD CONSTRAINT detalle_pedido_pkey PRIMARY KEY (id);


--
-- Name: detalle_venta detalle_venta_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.detalle_venta
    ADD CONSTRAINT detalle_venta_pkey PRIMARY KEY (id);


--
-- Name: empleado empleado_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.empleado
    ADD CONSTRAINT empleado_pkey PRIMARY KEY (id);


--
-- Name: etapa_produccion etapa_produccion_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.etapa_produccion
    ADD CONSTRAINT etapa_produccion_pkey PRIMARY KEY (id);


--
-- Name: gasto gasto_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gasto
    ADD CONSTRAINT gasto_pkey PRIMARY KEY (id);


--
-- Name: inventario inventario_material_id_ubicacion_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventario
    ADD CONSTRAINT inventario_material_id_ubicacion_id_key UNIQUE (material_id, ubicacion_id);


--
-- Name: inventario inventario_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventario
    ADD CONSTRAINT inventario_pkey PRIMARY KEY (id);


--
-- Name: mano_obra mano_obra_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.mano_obra
    ADD CONSTRAINT mano_obra_pkey PRIMARY KEY (id);


--
-- Name: material material_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.material
    ADD CONSTRAINT material_pkey PRIMARY KEY (id);


--
-- Name: moneda moneda_codigo_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.moneda
    ADD CONSTRAINT moneda_codigo_key UNIQUE (codigo);


--
-- Name: moneda moneda_nombre_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.moneda
    ADD CONSTRAINT moneda_nombre_key UNIQUE (nombre);


--
-- Name: moneda moneda_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.moneda
    ADD CONSTRAINT moneda_pkey PRIMARY KEY (id);


--
-- Name: movimiento_inventario movimiento_inventario_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.movimiento_inventario
    ADD CONSTRAINT movimiento_inventario_pkey PRIMARY KEY (id);


--
-- Name: orden_produccion orden_produccion_detalle_pedido_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.orden_produccion
    ADD CONSTRAINT orden_produccion_detalle_pedido_id_key UNIQUE (detalle_pedido_id);


--
-- Name: orden_produccion orden_produccion_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.orden_produccion
    ADD CONSTRAINT orden_produccion_pkey PRIMARY KEY (id);


--
-- Name: pago pago_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pago
    ADD CONSTRAINT pago_pkey PRIMARY KEY (id);


--
-- Name: pedido pedido_cotizacion_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pedido
    ADD CONSTRAINT pedido_cotizacion_id_key UNIQUE (cotizacion_id);


--
-- Name: pedido pedido_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pedido
    ADD CONSTRAINT pedido_pkey PRIMARY KEY (id);


--
-- Name: producto producto_codigo_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.producto
    ADD CONSTRAINT producto_codigo_key UNIQUE (codigo);


--
-- Name: producto producto_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.producto
    ADD CONSTRAINT producto_pkey PRIMARY KEY (id);


--
-- Name: proveedor proveedor_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.proveedor
    ADD CONSTRAINT proveedor_pkey PRIMARY KEY (id);


--
-- Name: rol rol_nombre_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rol
    ADD CONSTRAINT rol_nombre_key UNIQUE (nombre);


--
-- Name: rol rol_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rol
    ADD CONSTRAINT rol_pkey PRIMARY KEY (id);


--
-- Name: tasa_cambio tasa_cambio_moneda_origen_id_moneda_destino_id_fecha_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tasa_cambio
    ADD CONSTRAINT tasa_cambio_moneda_origen_id_moneda_destino_id_fecha_key UNIQUE (moneda_origen_id, moneda_destino_id, fecha);


--
-- Name: tasa_cambio tasa_cambio_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tasa_cambio
    ADD CONSTRAINT tasa_cambio_pkey PRIMARY KEY (id);


--
-- Name: tipo_gasto tipo_gasto_nombre_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tipo_gasto
    ADD CONSTRAINT tipo_gasto_nombre_key UNIQUE (nombre);


--
-- Name: tipo_gasto tipo_gasto_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tipo_gasto
    ADD CONSTRAINT tipo_gasto_pkey PRIMARY KEY (id);


--
-- Name: tipo_producto tipo_producto_nombre_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tipo_producto
    ADD CONSTRAINT tipo_producto_nombre_key UNIQUE (nombre);


--
-- Name: tipo_producto tipo_producto_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tipo_producto
    ADD CONSTRAINT tipo_producto_pkey PRIMARY KEY (id);


--
-- Name: ubicacion ubicacion_nombre_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ubicacion
    ADD CONSTRAINT ubicacion_nombre_key UNIQUE (nombre);


--
-- Name: ubicacion ubicacion_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ubicacion
    ADD CONSTRAINT ubicacion_pkey PRIMARY KEY (id);


--
-- Name: unidad_medida unidad_medida_nombre_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.unidad_medida
    ADD CONSTRAINT unidad_medida_nombre_key UNIQUE (nombre);


--
-- Name: unidad_medida unidad_medida_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.unidad_medida
    ADD CONSTRAINT unidad_medida_pkey PRIMARY KEY (id);


--
-- Name: usuario_rol uq_usuario_rol; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.usuario_rol
    ADD CONSTRAINT uq_usuario_rol UNIQUE (usuario_id, rol_id);


--
-- Name: usuario usuario_email_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.usuario
    ADD CONSTRAINT usuario_email_key UNIQUE (email);


--
-- Name: usuario usuario_empleado_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.usuario
    ADD CONSTRAINT usuario_empleado_id_key UNIQUE (empleado_id);


--
-- Name: usuario usuario_nombre_usuario_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.usuario
    ADD CONSTRAINT usuario_nombre_usuario_key UNIQUE (nombre_usuario);


--
-- Name: usuario usuario_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.usuario
    ADD CONSTRAINT usuario_pkey PRIMARY KEY (id);


--
-- Name: usuario_rol usuario_rol_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.usuario_rol
    ADD CONSTRAINT usuario_rol_pkey PRIMARY KEY (id);


--
-- Name: venta venta_pedido_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.venta
    ADD CONSTRAINT venta_pedido_id_key UNIQUE (pedido_id);


--
-- Name: venta venta_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.venta
    ADD CONSTRAINT venta_pkey PRIMARY KEY (id);


--
-- Name: idx_compra_moneda; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_compra_moneda ON public.compra USING btree (moneda_id);


--
-- Name: idx_compra_proveedor; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_compra_proveedor ON public.compra USING btree (proveedor_id);


--
-- Name: idx_consumo_etapa; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_consumo_etapa ON public.consumo_material USING btree (etapa_produccion_id);


--
-- Name: idx_consumo_material_fk; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_consumo_material_fk ON public.consumo_material USING btree (material_id);


--
-- Name: idx_cotizacion_cliente; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_cotizacion_cliente ON public.cotizacion USING btree (cliente_id);


--
-- Name: idx_detalle_compra_compra; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_detalle_compra_compra ON public.detalle_compra USING btree (compra_id);


--
-- Name: idx_detalle_compra_material; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_detalle_compra_material ON public.detalle_compra USING btree (material_id);


--
-- Name: idx_detalle_pedido_pedido; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_detalle_pedido_pedido ON public.detalle_pedido USING btree (pedido_id);


--
-- Name: idx_detalle_pedido_producto; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_detalle_pedido_producto ON public.detalle_pedido USING btree (producto_id);


--
-- Name: idx_detalle_venta_producto; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_detalle_venta_producto ON public.detalle_venta USING btree (producto_id);


--
-- Name: idx_detalle_venta_venta; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_detalle_venta_venta ON public.detalle_venta USING btree (venta_id);


--
-- Name: idx_empleado_cargo; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_empleado_cargo ON public.empleado USING btree (cargo_id);


--
-- Name: idx_etapa_area; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_etapa_area ON public.etapa_produccion USING btree (area_id);


--
-- Name: idx_etapa_empleado; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_etapa_empleado ON public.etapa_produccion USING btree (empleado_responsable_id);


--
-- Name: idx_etapa_estado; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_etapa_estado ON public.etapa_produccion USING btree (estado);


--
-- Name: idx_etapa_orden; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_etapa_orden ON public.etapa_produccion USING btree (orden_produccion_id);


--
-- Name: idx_gasto_moneda; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_gasto_moneda ON public.gasto USING btree (moneda_id);


--
-- Name: idx_gasto_tipo; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_gasto_tipo ON public.gasto USING btree (tipo_gasto_id);


--
-- Name: idx_inventario_material; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_inventario_material ON public.inventario USING btree (material_id);


--
-- Name: idx_inventario_ubicacion; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_inventario_ubicacion ON public.inventario USING btree (ubicacion_id);


--
-- Name: idx_mano_obra_empleado; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_mano_obra_empleado ON public.mano_obra USING btree (empleado_id);


--
-- Name: idx_mano_obra_etapa; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_mano_obra_etapa ON public.mano_obra USING btree (etapa_produccion_id);


--
-- Name: idx_material_unidad; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_material_unidad ON public.material USING btree (unidad_medida_id);


--
-- Name: idx_movimiento_fecha; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_movimiento_fecha ON public.movimiento_inventario USING btree (fecha);


--
-- Name: idx_movimiento_material; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_movimiento_material ON public.movimiento_inventario USING btree (material_id);


--
-- Name: idx_movimiento_ubicacion; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_movimiento_ubicacion ON public.movimiento_inventario USING btree (ubicacion_id);


--
-- Name: idx_orden_produccion_estado; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_orden_produccion_estado ON public.orden_produccion USING btree (estado);


--
-- Name: idx_pago_fecha; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_pago_fecha ON public.pago USING btree (fecha);


--
-- Name: idx_pago_moneda; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_pago_moneda ON public.pago USING btree (moneda_id);


--
-- Name: idx_pago_venta; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_pago_venta ON public.pago USING btree (venta_id);


--
-- Name: idx_pedido_cliente; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_pedido_cliente ON public.pedido USING btree (cliente_id);


--
-- Name: idx_pedido_estado; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_pedido_estado ON public.pedido USING btree (estado);


--
-- Name: idx_producto_tipo; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_producto_tipo ON public.producto USING btree (tipo_producto_id);


--
-- Name: idx_tasa_cambio_destino; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_tasa_cambio_destino ON public.tasa_cambio USING btree (moneda_destino_id);


--
-- Name: idx_tasa_cambio_origen; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_tasa_cambio_origen ON public.tasa_cambio USING btree (moneda_origen_id);


--
-- Name: idx_usuario_empleado; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_usuario_empleado ON public.usuario USING btree (empleado_id);


--
-- Name: idx_usuario_rol_rol; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_usuario_rol_rol ON public.usuario_rol USING btree (rol_id);


--
-- Name: idx_usuario_rol_usuario; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_usuario_rol_usuario ON public.usuario_rol USING btree (usuario_id);


--
-- Name: idx_venta_cliente; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_venta_cliente ON public.venta USING btree (cliente_id);


--
-- Name: idx_venta_estado; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_venta_estado ON public.venta USING btree (estado);


--
-- Name: idx_venta_moneda; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_venta_moneda ON public.venta USING btree (moneda_id);


--
-- Name: area trg_area_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_area_updated BEFORE UPDATE ON public.area FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: cargo trg_cargo_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_cargo_updated BEFORE UPDATE ON public.cargo FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: cliente trg_cliente_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_cliente_updated BEFORE UPDATE ON public.cliente FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: compra trg_compra_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_compra_updated BEFORE UPDATE ON public.compra FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: consumo_material trg_consumo_material_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_consumo_material_updated BEFORE UPDATE ON public.consumo_material FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: costo_produccion trg_costo_produccion_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_costo_produccion_updated BEFORE UPDATE ON public.costo_produccion FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: cotizacion trg_cotizacion_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_cotizacion_updated BEFORE UPDATE ON public.cotizacion FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: detalle_compra trg_detalle_compra_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_detalle_compra_updated BEFORE UPDATE ON public.detalle_compra FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: detalle_pedido trg_detalle_pedido_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_detalle_pedido_updated BEFORE UPDATE ON public.detalle_pedido FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: detalle_venta trg_detalle_venta_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_detalle_venta_updated BEFORE UPDATE ON public.detalle_venta FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: empleado trg_empleado_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_empleado_updated BEFORE UPDATE ON public.empleado FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: etapa_produccion trg_etapa_produccion_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_etapa_produccion_updated BEFORE UPDATE ON public.etapa_produccion FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: gasto trg_gasto_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_gasto_updated BEFORE UPDATE ON public.gasto FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: inventario trg_inventario_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_inventario_updated BEFORE UPDATE ON public.inventario FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: mano_obra trg_mano_obra_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_mano_obra_updated BEFORE UPDATE ON public.mano_obra FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: material trg_material_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_material_updated BEFORE UPDATE ON public.material FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: moneda trg_moneda_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_moneda_updated BEFORE UPDATE ON public.moneda FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: movimiento_inventario trg_movimiento_inventario_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_movimiento_inventario_updated BEFORE UPDATE ON public.movimiento_inventario FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: orden_produccion trg_orden_produccion_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_orden_produccion_updated BEFORE UPDATE ON public.orden_produccion FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: pago trg_pago_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_pago_updated BEFORE UPDATE ON public.pago FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: pedido trg_pedido_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_pedido_updated BEFORE UPDATE ON public.pedido FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: producto trg_producto_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_producto_updated BEFORE UPDATE ON public.producto FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: proveedor trg_proveedor_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_proveedor_updated BEFORE UPDATE ON public.proveedor FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: rol trg_rol_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_rol_updated BEFORE UPDATE ON public.rol FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: tasa_cambio trg_tasa_cambio_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_tasa_cambio_updated BEFORE UPDATE ON public.tasa_cambio FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: tipo_gasto trg_tipo_gasto_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_tipo_gasto_updated BEFORE UPDATE ON public.tipo_gasto FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: tipo_producto trg_tipo_producto_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_tipo_producto_updated BEFORE UPDATE ON public.tipo_producto FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: ubicacion trg_ubicacion_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_ubicacion_updated BEFORE UPDATE ON public.ubicacion FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: unidad_medida trg_unidad_medida_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_unidad_medida_updated BEFORE UPDATE ON public.unidad_medida FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: usuario_rol trg_usuario_rol_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_usuario_rol_updated BEFORE UPDATE ON public.usuario_rol FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: usuario trg_usuario_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_usuario_updated BEFORE UPDATE ON public.usuario FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: venta trg_venta_updated; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_venta_updated BEFORE UPDATE ON public.venta FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: compra compra_moneda_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.compra
    ADD CONSTRAINT compra_moneda_id_fkey FOREIGN KEY (moneda_id) REFERENCES public.moneda(id) ON DELETE RESTRICT;


--
-- Name: compra compra_proveedor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.compra
    ADD CONSTRAINT compra_proveedor_id_fkey FOREIGN KEY (proveedor_id) REFERENCES public.proveedor(id) ON DELETE RESTRICT;


--
-- Name: consumo_material consumo_material_etapa_produccion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.consumo_material
    ADD CONSTRAINT consumo_material_etapa_produccion_id_fkey FOREIGN KEY (etapa_produccion_id) REFERENCES public.etapa_produccion(id) ON DELETE CASCADE;


--
-- Name: consumo_material consumo_material_material_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.consumo_material
    ADD CONSTRAINT consumo_material_material_id_fkey FOREIGN KEY (material_id) REFERENCES public.material(id) ON DELETE RESTRICT;


--
-- Name: costo_produccion costo_produccion_orden_produccion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.costo_produccion
    ADD CONSTRAINT costo_produccion_orden_produccion_id_fkey FOREIGN KEY (orden_produccion_id) REFERENCES public.orden_produccion(id) ON DELETE CASCADE;


--
-- Name: cotizacion cotizacion_cliente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cotizacion
    ADD CONSTRAINT cotizacion_cliente_id_fkey FOREIGN KEY (cliente_id) REFERENCES public.cliente(id) ON DELETE RESTRICT;


--
-- Name: detalle_compra detalle_compra_compra_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.detalle_compra
    ADD CONSTRAINT detalle_compra_compra_id_fkey FOREIGN KEY (compra_id) REFERENCES public.compra(id) ON DELETE CASCADE;


--
-- Name: detalle_compra detalle_compra_material_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.detalle_compra
    ADD CONSTRAINT detalle_compra_material_id_fkey FOREIGN KEY (material_id) REFERENCES public.material(id) ON DELETE RESTRICT;


--
-- Name: detalle_pedido detalle_pedido_pedido_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.detalle_pedido
    ADD CONSTRAINT detalle_pedido_pedido_id_fkey FOREIGN KEY (pedido_id) REFERENCES public.pedido(id) ON DELETE CASCADE;


--
-- Name: detalle_pedido detalle_pedido_producto_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.detalle_pedido
    ADD CONSTRAINT detalle_pedido_producto_id_fkey FOREIGN KEY (producto_id) REFERENCES public.producto(id) ON DELETE RESTRICT;


--
-- Name: detalle_venta detalle_venta_producto_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.detalle_venta
    ADD CONSTRAINT detalle_venta_producto_id_fkey FOREIGN KEY (producto_id) REFERENCES public.producto(id) ON DELETE RESTRICT;


--
-- Name: detalle_venta detalle_venta_venta_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.detalle_venta
    ADD CONSTRAINT detalle_venta_venta_id_fkey FOREIGN KEY (venta_id) REFERENCES public.venta(id) ON DELETE CASCADE;


--
-- Name: empleado empleado_cargo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.empleado
    ADD CONSTRAINT empleado_cargo_id_fkey FOREIGN KEY (cargo_id) REFERENCES public.cargo(id) ON DELETE RESTRICT;


--
-- Name: etapa_produccion etapa_produccion_area_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.etapa_produccion
    ADD CONSTRAINT etapa_produccion_area_id_fkey FOREIGN KEY (area_id) REFERENCES public.area(id) ON DELETE RESTRICT;


--
-- Name: etapa_produccion etapa_produccion_empleado_responsable_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.etapa_produccion
    ADD CONSTRAINT etapa_produccion_empleado_responsable_id_fkey FOREIGN KEY (empleado_responsable_id) REFERENCES public.empleado(id) ON DELETE RESTRICT;


--
-- Name: etapa_produccion etapa_produccion_orden_produccion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.etapa_produccion
    ADD CONSTRAINT etapa_produccion_orden_produccion_id_fkey FOREIGN KEY (orden_produccion_id) REFERENCES public.orden_produccion(id) ON DELETE CASCADE;


--
-- Name: usuario fk_usuario_empleado; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.usuario
    ADD CONSTRAINT fk_usuario_empleado FOREIGN KEY (empleado_id) REFERENCES public.empleado(id) ON DELETE SET NULL;


--
-- Name: usuario_rol fk_usuario_rol_rol; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.usuario_rol
    ADD CONSTRAINT fk_usuario_rol_rol FOREIGN KEY (rol_id) REFERENCES public.rol(id) ON DELETE RESTRICT;


--
-- Name: usuario_rol fk_usuario_rol_usuario; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.usuario_rol
    ADD CONSTRAINT fk_usuario_rol_usuario FOREIGN KEY (usuario_id) REFERENCES public.usuario(id) ON DELETE CASCADE;


--
-- Name: gasto gasto_moneda_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gasto
    ADD CONSTRAINT gasto_moneda_id_fkey FOREIGN KEY (moneda_id) REFERENCES public.moneda(id) ON DELETE RESTRICT;


--
-- Name: gasto gasto_tipo_gasto_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gasto
    ADD CONSTRAINT gasto_tipo_gasto_id_fkey FOREIGN KEY (tipo_gasto_id) REFERENCES public.tipo_gasto(id) ON DELETE RESTRICT;


--
-- Name: inventario inventario_material_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventario
    ADD CONSTRAINT inventario_material_id_fkey FOREIGN KEY (material_id) REFERENCES public.material(id) ON DELETE RESTRICT;


--
-- Name: inventario inventario_ubicacion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventario
    ADD CONSTRAINT inventario_ubicacion_id_fkey FOREIGN KEY (ubicacion_id) REFERENCES public.ubicacion(id) ON DELETE RESTRICT;


--
-- Name: mano_obra mano_obra_empleado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.mano_obra
    ADD CONSTRAINT mano_obra_empleado_id_fkey FOREIGN KEY (empleado_id) REFERENCES public.empleado(id) ON DELETE RESTRICT;


--
-- Name: mano_obra mano_obra_etapa_produccion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.mano_obra
    ADD CONSTRAINT mano_obra_etapa_produccion_id_fkey FOREIGN KEY (etapa_produccion_id) REFERENCES public.etapa_produccion(id) ON DELETE CASCADE;


--
-- Name: material material_unidad_medida_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.material
    ADD CONSTRAINT material_unidad_medida_id_fkey FOREIGN KEY (unidad_medida_id) REFERENCES public.unidad_medida(id) ON DELETE RESTRICT;


--
-- Name: movimiento_inventario movimiento_inventario_material_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.movimiento_inventario
    ADD CONSTRAINT movimiento_inventario_material_id_fkey FOREIGN KEY (material_id) REFERENCES public.material(id) ON DELETE RESTRICT;


--
-- Name: movimiento_inventario movimiento_inventario_ubicacion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.movimiento_inventario
    ADD CONSTRAINT movimiento_inventario_ubicacion_id_fkey FOREIGN KEY (ubicacion_id) REFERENCES public.ubicacion(id) ON DELETE RESTRICT;


--
-- Name: orden_produccion orden_produccion_detalle_pedido_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.orden_produccion
    ADD CONSTRAINT orden_produccion_detalle_pedido_id_fkey FOREIGN KEY (detalle_pedido_id) REFERENCES public.detalle_pedido(id) ON DELETE RESTRICT;


--
-- Name: pago pago_moneda_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pago
    ADD CONSTRAINT pago_moneda_id_fkey FOREIGN KEY (moneda_id) REFERENCES public.moneda(id) ON DELETE RESTRICT;


--
-- Name: pago pago_venta_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pago
    ADD CONSTRAINT pago_venta_id_fkey FOREIGN KEY (venta_id) REFERENCES public.venta(id) ON DELETE RESTRICT;


--
-- Name: pedido pedido_cliente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pedido
    ADD CONSTRAINT pedido_cliente_id_fkey FOREIGN KEY (cliente_id) REFERENCES public.cliente(id) ON DELETE RESTRICT;


--
-- Name: pedido pedido_cotizacion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pedido
    ADD CONSTRAINT pedido_cotizacion_id_fkey FOREIGN KEY (cotizacion_id) REFERENCES public.cotizacion(id) ON DELETE RESTRICT;


--
-- Name: producto producto_tipo_producto_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.producto
    ADD CONSTRAINT producto_tipo_producto_id_fkey FOREIGN KEY (tipo_producto_id) REFERENCES public.tipo_producto(id) ON DELETE RESTRICT;


--
-- Name: tasa_cambio tasa_cambio_moneda_destino_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tasa_cambio
    ADD CONSTRAINT tasa_cambio_moneda_destino_id_fkey FOREIGN KEY (moneda_destino_id) REFERENCES public.moneda(id) ON DELETE RESTRICT;


--
-- Name: tasa_cambio tasa_cambio_moneda_origen_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tasa_cambio
    ADD CONSTRAINT tasa_cambio_moneda_origen_id_fkey FOREIGN KEY (moneda_origen_id) REFERENCES public.moneda(id) ON DELETE RESTRICT;


--
-- Name: venta venta_cliente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.venta
    ADD CONSTRAINT venta_cliente_id_fkey FOREIGN KEY (cliente_id) REFERENCES public.cliente(id) ON DELETE RESTRICT;


--
-- Name: venta venta_moneda_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.venta
    ADD CONSTRAINT venta_moneda_id_fkey FOREIGN KEY (moneda_id) REFERENCES public.moneda(id) ON DELETE RESTRICT;


--
-- Name: venta venta_pedido_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.venta
    ADD CONSTRAINT venta_pedido_id_fkey FOREIGN KEY (pedido_id) REFERENCES public.pedido(id) ON DELETE RESTRICT;


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: postgres
--

REVOKE USAGE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO yeikar;


--
-- Name: TABLE area; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.area TO yeikar;


--
-- Name: TABLE cargo; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.cargo TO yeikar;


--
-- Name: TABLE cliente; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.cliente TO yeikar;


--
-- Name: TABLE compra; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.compra TO yeikar;


--
-- Name: TABLE consumo_material; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.consumo_material TO yeikar;


--
-- Name: TABLE costo_produccion; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.costo_produccion TO yeikar;


--
-- Name: TABLE cotizacion; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.cotizacion TO yeikar;


--
-- Name: TABLE detalle_compra; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.detalle_compra TO yeikar;


--
-- Name: TABLE detalle_pedido; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.detalle_pedido TO yeikar;


--
-- Name: TABLE detalle_venta; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.detalle_venta TO yeikar;


--
-- Name: TABLE empleado; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.empleado TO yeikar;


--
-- Name: TABLE etapa_produccion; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.etapa_produccion TO yeikar;


--
-- Name: TABLE gasto; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.gasto TO yeikar;


--
-- Name: TABLE inventario; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.inventario TO yeikar;


--
-- Name: TABLE mano_obra; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.mano_obra TO yeikar;


--
-- Name: TABLE material; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.material TO yeikar;


--
-- Name: TABLE moneda; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.moneda TO yeikar;


--
-- Name: TABLE movimiento_inventario; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.movimiento_inventario TO yeikar;


--
-- Name: TABLE orden_produccion; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.orden_produccion TO yeikar;


--
-- Name: TABLE pago; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.pago TO yeikar;


--
-- Name: TABLE pedido; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.pedido TO yeikar;


--
-- Name: TABLE producto; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.producto TO yeikar;


--
-- Name: TABLE proveedor; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.proveedor TO yeikar;


--
-- Name: TABLE rol; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.rol TO yeikar;


--
-- Name: TABLE tasa_cambio; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.tasa_cambio TO yeikar;


--
-- Name: TABLE tipo_gasto; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.tipo_gasto TO yeikar;


--
-- Name: TABLE tipo_producto; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.tipo_producto TO yeikar;


--
-- Name: TABLE ubicacion; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.ubicacion TO yeikar;


--
-- Name: TABLE unidad_medida; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.unidad_medida TO yeikar;


--
-- Name: TABLE usuario; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.usuario TO yeikar;


--
-- Name: TABLE usuario_rol; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.usuario_rol TO yeikar;


--
-- Name: TABLE venta; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.venta TO yeikar;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: public; Owner: postgres
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT ON TABLES TO yeikar;


--
-- PostgreSQL database dump complete
--

\unrestrict MzzuR5HfkLog6V9oRO4NVKzCErxLwr7jUpdgwmawLshHUmVakNu0TxblxiTpRox

