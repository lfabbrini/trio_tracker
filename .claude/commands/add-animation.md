# Add Animation Command

Add a CSS animation to Trio Tracker.

## Instructions

Animations are defined in `app/templates/base.html` inside the `<style>` section.

## Animation Structure

```css
/* Animation definition */
@keyframes animationName {
    0% { 
        /* Start state */
        transform: translateY(0);
        opacity: 1;
    }
    50% {
        /* Middle state (optional) */
        transform: translateY(-10px);
        opacity: 0.5;
    }
    100% { 
        /* End state */
        transform: translateY(0);
        opacity: 1;
    }
}

/* Class that applies the animation */
.animated-element {
    animation: animationName 2s ease-in-out infinite;
}
```

## Common Transform Properties

| Property | Effect |
|----------|--------|
| `translateX(10px)` | Move right 10px |
| `translateY(-5px)` | Move up 5px |
| `scale(1.2)` | Scale to 120% |
| `scaleX(-1)` | Flip horizontally |
| `rotate(15deg)` | Rotate 15 degrees |

## Animation Timing

| Value | Effect |
|-------|--------|
| `ease` | Default, smooth |
| `ease-in` | Slow start |
| `ease-out` | Slow end |
| `ease-in-out` | Slow start and end |
| `linear` | Constant speed |

## Animation Request

$ARGUMENTS
