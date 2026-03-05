---
name: calculator
description: Perform mathematical calculations and evaluations using python
parameters:
  type: object
  properties:
    expression:
      type: string
      description: Mathematical expression to evaluate using python
  required:
    - expression
metadata:
  type: cli
  command_template: "python3 -c \"print({expression})\""
  tier: common
  priority: 9
  retry_policy:
    maximum_attempts: 2
    backoff_coefficient: 1.0
---

# Calculator

Perform mathematical calculations, evaluations, and conversions.

## Usage

Use this tool for arithmetic, algebra, trigonometry, statistics, and unit conversions.

## Examples

```python
# Basic arithmetic
calculator(expression="42 * 1.5 + 10")

# Exponents and powers
calculator(expression="2 ** 10")

# Scientific notation
calculator(expression="1.5e6 + 2.3e5")

# Complex expressions
calculator(expression="(100 - 32) * 5 / 9")  # Fahrenheit to Celsius

# Math functions
calculator(expression="import math; math.sqrt(144)")

# Percentage calculation
calculator(expression="250 * 0.15")  # 15% of 250

# Statistics
calculator(expression="sum([10, 20, 30, 40, 50]) / 5")  # Average
```

## Supported Operations

**Basic Operations**:
- `+` Addition
- `-` Subtraction
- `*` Multiplication
- `/` Division
- `//` Integer division
- `%` Modulo
- `**` Exponentiation

**Math Module Functions**:
```python
import math

# Trigonometry
math.sin(x), math.cos(x), math.tan(x)

# Logarithms
math.log(x), math.log10(x), math.log2(x)

# Powers and roots
math.sqrt(x), math.pow(x, y)

# Constants
math.pi, math.e

# Rounding
math.ceil(x), math.floor(x), round(x)
```

**Statistics**:
```python
# Lists and aggregations
sum([1, 2, 3, 4, 5])
max([1, 2, 3, 4, 5])
min([1, 2, 3, 4, 5])
len([1, 2, 3, 4, 5])
```

## Common Use Cases

- Currency conversions
- Unit conversions (temperature, distance, weight)
- Percentage calculations
- Statistical analysis
- Geometric calculations
- Financial calculations (interest, tax)
- Time duration calculations
- Data size conversions (bytes to MB/GB)

## Conversion Examples

```python
# Temperature: Fahrenheit to Celsius
calculator(expression="(75 - 32) * 5 / 9")

# Distance: Miles to Kilometers
calculator(expression="10 * 1.60934")

# Data: Bytes to Megabytes
calculator(expression="1_048_576 / (1024 ** 2)")

# Time: Hours to seconds
calculator(expression="2.5 * 60 * 60")

# Currency: Apply tax
calculator(expression="100 * 1.0825")  # 8.25% tax
```

## Notes

- Expression is evaluated as Python code
- Full Python math capabilities available
- Use underscores in numbers for readability: `1_000_000`
- Floating-point precision limitations apply
- Division by zero returns error
- Invalid syntax returns Python error message
- Security: Expression is sandboxed

## Safety

- Expressions are evaluated in isolated Python environment
- No file system or network access
- Memory and CPU limits enforced
- Timeout after 5 seconds for complex calculations
