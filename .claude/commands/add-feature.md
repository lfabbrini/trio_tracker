# Add Feature Command

Add a new feature to Trio Tracker following the established patterns.

## Instructions

When adding a new feature, follow these steps in order:

1. **Database Layer** (`app/database.py`)
   - Add query function to retrieve/manipulate data
   - Follow existing patterns (use `get_connection()` context manager)

2. **Backend Routes** (`app/main.py`)
   - Add data to `index()` template context
   - Add data to `record_match()` template context (if it should update on match recording)
   - Create new `/partials/xxx` GET route for HTMX refresh

3. **Partial Template** (`app/templates/partials/xxx.html`)
   - Create the HTML fragment
   - Use existing styling patterns (card-glow, Tailwind classes)

4. **Main Page** (`app/templates/index.html`)
   - Add card container with `{% include "partials/xxx.html" %}`
   - Add `hx-get="/partials/xxx"` and `hx-trigger="every 30s"` for auto-refresh
   - Give container a unique `id` for HTMX targeting

5. **OOB Updates** (`app/templates/partials/all_stats.html`)
   - Add `<div id="xxx" hx-swap-oob="true">{% include "partials/xxx.html" %}</div>`

## Feature Request

$ARGUMENTS
