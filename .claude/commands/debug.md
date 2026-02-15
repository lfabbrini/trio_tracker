# Debug Command

Help debug an issue with Trio Tracker.

## Debugging Steps

1. **Check Docker logs**
   ```bash
   docker-compose logs -f
   ```

2. **Common Issues**

   | Symptom | Likely Cause | Solution |
   |---------|--------------|----------|
   | Internal Server Error | Python/Jinja2 error | Check logs for traceback |
   | Page not updating | HTMX target mismatch | Verify `id` matches `hx-target` |
   | 404 on partial | Route not defined | Add route in `main.py` |
   | Empty data | Missing context variable | Add to template context |
   | Style not applied | Class typo | Check Tailwind class names |

3. **Database Check**
   ```bash
   docker-compose exec trio-tracker sqlite3 /app/data/trio.db "SELECT * FROM players;"
   ```

4. **Network Check** (Browser DevTools)
   - Open Network tab
   - Look for failed requests (red)
   - Check response content

## Issue Description

$ARGUMENTS
