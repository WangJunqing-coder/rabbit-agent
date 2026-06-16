from textual.widgets import Input
from textual.message import Message
import inspect

# Show Input.Submitted definition
src = inspect.getsource(Input.Submitted)
print("=== Input.Submitted source ===")
print(src)
print()

# Show other widget Submitted patterns
from textual.widgets._text_area import TextArea
print("TextArea bases:", TextArea.__mro__[:4])

# Check if TextArea has any Submitted-like messages
print("TextArea inner classes:", [n for n in dir(TextArea) if n[0].isupper() and n == n.upper() or (n[0].isupper() and isinstance(getattr(TextArea, n, None), type) and issubclass(getattr(TextArea, n), Message) if hasattr(getattr(TextArea, n, None), '__mro__') else False)])
