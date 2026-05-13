# PROY-2026-GRUPO-3

<p align="center">
  <img src="./full_logo.png" alt="AquaSense Logo" width="320"/>
</p>

Repositorio del grupo 3 para el proyecto del ramo *Proyecto Inicial (IWG400)* – 2026.

## 👥 Integrantes del grupo

| Nombre y Apellido | Usuario GitHub | Correo USM               | Rol USM      |
| ----------------- | -------------- | ------------------------ | ------------ |
| Lucas Fluxá       | @LucasFluxa    | lfluxa@usm.cl            | 202630017-k  |
| Bruno Olguín      | @Bruno-Olguin  | bolguinc@usm.cl          | 202630028-5  |
| Domingo Vargas    | @Domingo-07    | jvargascar@usm.cl        | 202630026-9  |
| Daniel Guerra     | @dannyto2      | dguerrap@usm.cl          | 202530020-6  |

---

## 📝 Descripción breve del proyecto

**AquaSense** es un sistema inteligente de monitoreo de acuarios que combina sensores físicos y una interfaz web local. El sistema mide en tiempo real la temperatura y pH del agua, y utiliza una cámara USB para visualización en vivo del acuario. Todo el procesamiento ocurre directamente en el Arduino UNO Q, sin depender de servidores externos.

El dashboard web incluye una base de datos de especies de peces con parámetros ideales de temperatura y pH, compatibilidad entre especies, y un sistema de alertas automáticas cuando los parámetros del agua salen del rango óptimo para las especies registradas.

---

## 🎯 Objetivos

- **Objetivo general:**
  - Desarrollar un sistema de monitoreo inteligente de acuarios que permita detectar condiciones adversas del agua y comportamiento anómalo de los peces en tiempo real.

- **Objetivos específicos:**
  - Medir temperatura y pH mediante sensores conectados al Arduino UNO Q.
  - Visualizar en vivo el acuario mediante cámara USB integrada en el dashboard.
  - Desarrollar un dashboard web hosteado en el propio Arduino UNO Q accesible desde cualquier dispositivo en la misma red.
  - Generar alertas automáticas cuando algún parámetro salga del rango ideal para las especies registradas.
  - Permitir al usuario registrar las especies de peces de su acuario y consultar su compatibilidad y parámetros ideales.

---

## 🧩 Alcance del proyecto

**Dentro del alcance:**
- Monitoreo en tiempo real de temperatura y pH
- Visualización en vivo del acuario mediante cámara USB
- Dashboard web local con historial de datos y gráficos en tiempo real
- Base de datos de 32 especies de peces con parámetros ideales y compatibilidad entre pares
- Alertas cuando los parámetros salen del rango óptimo para las especies del acuario

**Fuera del alcance:**
- Control automatizado de equipos del acuario (calefactor, filtro, etc.)

---

## 🛠️ Tecnologías y herramientas utilizadas

- **Lenguaje(s) de programación:**
  - Python (servidor del dashboard)
  - C++ / Arduino Sketch (control en tiempo real del STM32U585)
  - JavaScript / HTML / CSS (interfaz web del dashboard)

- **Microcontroladores:**
  - Arduino UNO Q (Qualcomm Dragonwing QRB2210 + STM32U585)

- **Sensores:**
  - DS18B20 — temperatura del agua (sumergible, OneWire)
  - pH-4502C — pH del agua (analógico, con placa de acondicionamiento)
  - Webcam USB — tracking de movimiento de peces (V4L2)

- **Software y librerías:**
  - Arduino WebUI — servidor web y comunicación en tiempo real integrados en el UNO Q
  - pyserial — comunicación serial STM32 → Python
  - OneWire + DallasTemperature — lectura del DS18B20
  - Chart.js — gráficos de historial de temperatura y pH

---

## 🗂️ Estructura del repositorio

```
Aquasens3/
├── assets/
│   ├── index.html          # Dashboard web (frontend completo)
│   ├── favicon.png         # Ícono del sitio
│   ├── fish_database.json  # Base de datos de 32 especies
│   ├── update_fish.json    # Compatibilidad entre pares de peces
│   └── fish_images/        # Imágenes de las especies
├── python/
│   └── main.py             # Servidor principal (Arduino UNO Q)
├── sketch/
│   └── sketch.ino          # Firmware STM32U585
├── logo.png                
├── full_logo.png           # Logos del proyecto
└── README.md
```

---

## 🚀 Instrucciones de Instalación y Uso

### Despliegue en Arduino UNO Q

> *Por definir* — pendiente de subida del firmware y configuración del entorno App Lab.

---

## 📐 Diseño del Sistema

![Diagrama de Conexiones](./assets/diagrama_conexiones.png)

*El STM32U585 lee los sensores de temperatura y pH y los envía al Qualcomm via comunicación interna. El Qualcomm corre Python y sirve el dashboard web mediante Arduino WebUI, accesible desde cualquier dispositivo en la red local.*

---

## 📅 Cronograma de trabajo

[Carta Gantt](https://lucasfluxa.github.io/Aquasense-Grupo3/Cartagantt.html)

---

## 📚 Bibliografía

- [Arduino UNO Q — Documentación oficial](https://docs.arduino.cc/hardware/uno-q/)
- [Arduino WebUI — Documentación oficial](https://docs.arduino.cc/arduino-cloud/features/webui/)
- [OneWire + DallasTemperature — Librería Arduino](https://github.com/milesburton/Arduino-Temperature-Control-Library)
- [Chart.js — Documentación oficial](https://www.chartjs.org/docs/)

---

## 📌 Notas adicionales

> - La cámara USB se conecta al puerto USB-C del UNO Q mediante un USB-C HUB.
> - El sensor de turbidez TSD-10 fue descartado del alcance actual del proyecto.
