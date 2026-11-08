# Changelog

## v2.0.0

### Agregado
- **Avisos por WhatsApp** vía CallMeBot, junto al mail: las 5 ofertas de mejor puntaje, partidas en varios mensajes con pausa si es largo. Comando `python -m radar probar-whatsapp` y configuración desde el panel.
- **Paquete `radar/notifiers/`** con una interfaz común (`Notificador.enviar(ofertas) -> Resultado`), los canales `email` y `whatsapp`, y el proveedor de WhatsApp separado del canal para sumar otro más adelante. Si un canal falla se sigue con el otro; una oferta queda avisada si llegó por al menos uno.
- **Ejecución diaria en GitHub Actions** (`radar-diario.yml`, 8:17 hora Argentina): `python -m radar resumen --ci`, sin panel, con el estado de las ofertas ya avisadas (solo hashes, 45 días) en la rama huérfana `radar-state`.
- `busqueda.fuentes_ci` (LinkedIn desactivado), `notificaciones.modo` (`local` | `ci`) para no recibir avisos repetidos, y el resumen menciona las fuentes que fallaron.
- **Etiqueta** «encaja» / «aplicá igual» y sus motivos en cada oferta, visibles en el mail y en WhatsApp.
- **Tests y CI:** suite de pytest (reglas del scoring, mensajes, notifiers con SMTP/HTTP simulados, estado, workflows) que bloquea el acceso a internet, y `tests.yml` con `ruff` y `pytest` en cada push y PR.

### Cambiado
- **Filtros alineados con el perfil:** React Native, TypeScript, Expo, Flask y scikit-learn pasan al stack propio; nuevos puestos objetivo (Analista de Datos / BI Jr, Cloud Jr); 2 años de experiencia es «aplicá igual» y 3 o más se excluye; el remoto desde el exterior que acepta Argentina/LATAM se mantiene; B2 alcanza para inglés «intermedio-avanzado»; part time y freelance restan sin excluir; la regla de portfolio considera los puestos objetivo.
- El stack propio, el ajeno y los puestos objetivo se leen de `config.json` (`perfil.*`).
- El prompt de IA evalúa contra los 3 puestos y respeta «aplicá igual».
- README reescrito (instalación, variables de entorno, uso local y en la nube, decisiones de diseño y uso responsable).

### Seguridad y privacidad
- Teléfono, mail, CV y postulaciones salen del repo (archivos ignorados + versiones `*.example.md`); el contacto sale de variables de entorno o del CV local.
- Los errores de WhatsApp no filtran la apikey ni el teléfono.

### Quitado
- Se sacó una excepción de la regla de portfolio que dejaba pasar «pasante/trainee» sin ninguna tecnología ni puesto objetivo.
