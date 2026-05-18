Antes de crear el PR, determiná el base branch ejecutando `git log --oneline --graph --decorate -20` para identificar desde qué branch salió el branch actual (el ancestro más reciente que no sea el branch actual).

Creá un PR desde el branch actual hacia ese base branch con estas reglas:

- Título: formato `[tipo]: descripción corta` (feat/fix/refactor/chore)
- Descripción en español
- Secciones: ## Cambios, ## Cómo probar, ## Notas
- Listá solo los archivos realmente modificados
- No incluyas archivos de configuración triviales en el resumen
- Usá `gh pr create` y mostrá la URL al final
