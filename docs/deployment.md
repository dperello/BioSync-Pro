# Documentación de Despliegue - BioSync Pro

## 1. Repositorio GitHub
El código se encuentra alojado en: `https://github.com/dperello/BioSync-Pro`

## 2. Instrucciones para actualización manual
Si deseas subir cambios manualmente desde tu terminal, utiliza estos comandos:

```bash
# Añadir cambios
git add .
# Crear commit
git commit -m "Descripción de los cambios"
# Subir al servidor
git push origin main
```

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
