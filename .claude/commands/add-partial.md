# Add Partial Command

Create a new HTMX partial template for Trio Tracker.

## Instructions

Create a new partial that:
1. Lives in `app/templates/partials/`
2. Follows existing styling (card-glow, Tailwind classes, DaisyUI components)
3. Handles empty state with a friendly message
4. Uses Jinja2 syntax for data display

## Template Structure

```html
{% if data_variable %}
<div class="space-y-2">
    {% for item in data_variable %}
    <div class="flex items-center gap-3 p-3 rounded-xl ...">
        <!-- Item content -->
    </div>
    {% endfor %}
</div>
{% else %}
<div class="text-center py-4 text-slate-500 text-sm">
    <p>No data yet</p>
</div>
{% endif %}
```

## Partial Request

$ARGUMENTS
