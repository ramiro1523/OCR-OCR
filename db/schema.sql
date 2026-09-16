-- Base de datos IEPPO
CREATE DATABASE ieppo;
\c ieppo;

-- Formularios procesados
CREATE TABLE formularios (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(200),
    sexo CHAR(1) CHECK (sexo IN ('M','F')),
    fecha_procesado TIMESTAMP DEFAULT NOW()
);

-- Marcas detectadas por ítem
CREATE TABLE marcas (
    id SERIAL PRIMARY KEY,
    formulario_id INT REFERENCES formularios(id) ON DELETE CASCADE,
    item VARCHAR(10) NOT NULL,
    opcion VARCHAR(10),  -- "no" | "si" | "ambos" | "vacio"
    puntaje INT DEFAULT 0,
    UNIQUE(formulario_id, item)
);

-- Puntajes por tipo vocacional
CREATE TABLE puntajes (
    id SERIAL PRIMARY KEY,
    formulario_id INT REFERENCES formularios(id) ON DELETE CASCADE,
    tipo VARCHAR(50) NOT NULL,
    pd INT,
    baremo INT,
    posicion INT,
    UNIQUE(formulario_id, tipo)
);

-- Carreras sugeridas
CREATE TABLE carreras_sugeridas (
    id SERIAL PRIMARY KEY,
    formulario_id INT REFERENCES formularios(id) ON DELETE CASCADE,
    carrera VARCHAR(200),
    tipo VARCHAR(50),
    es_principal BOOLEAN DEFAULT FALSE
);

-- Índices
CREATE INDEX idx_formularios_fecha ON formularios(fecha_procesado);
CREATE INDEX idx_marcas_formulario ON marcas(formulario_id);
CREATE INDEX idx_puntajes_formulario ON puntajes(formulario_id);