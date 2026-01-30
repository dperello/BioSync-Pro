## 1. Acceso a la Aplicación
**URL Definitiva:** [https://biosync-pro.streamlit.app/](https://biosync-pro.streamlit.app/)

## 2. Repositorio GitHub
El código se encuentra alojado en: `https://github.com/dperello/BioSync-Pro`

## 3. Instrucciones para actualización manual
Cuando hagas un cambio en el código local (`app.py`, etc.), sigue estos 3 pasos para que se reflejen en la web:

```bash
# 1. Preparar los archivos
git add .
# 2. Guardar el cambio localmente
git commit -m "Descripción de tu nueva mejora"
# 3. Subir a la nube
git push origin main
```

### ⏱️ ¿Cuánto tarda en replicarse?
- **Tiempo:** Suele tardar entre **30 y 60 segundos**.
- **Proceso:** Streamlit Cloud detecta el `push` automáticamente, reinstala las librerías (si has cambiado `requirements.txt`) y reinicia el servidor. Veras un pequeño icono de "Building" o "Processing" en la esquina inferior derecha de tu web durante ese tiempo.

## 3. Despliegue en Streamlit Cloud
1. Entra en [Streamlit Community Cloud](https://streamlit.io/cloud).
2. Conecta tu cuenta de GitHub.
3. Elige el repositorio `dperello/BioSync-Pro`.
4. El archivo principal es `app.py`.
5. ¡Pulsa Deploy!

## 4. Notas Técnicas
- El archivo `requirements.txt` contiene las librerías necesarias.
- El `.gitignore` evita subir archivos temporales y datos sensibles.
- El sistema de PDF requiere la librería `fpdf2` (incluida en requirements).
