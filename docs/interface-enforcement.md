# Interface Enforcement Strategy

## The Problem

Interfaces define contracts — "if you're a ProtocolAdapter, you MUST have these methods." But enforcement varies wildly by language. PHP gets this right natively. Python and JS need help.

## Current State

We use Python `ABC` with `@abstractmethod`:

```python
class ProtocolAdapter(ABC):
    @abstractmethod
    async def send(self, text: str): ...
    @abstractmethod
    async def get_char(self, prompt="") -> str: ...
```

**Weakness:** Only checked at instantiation, not import. If someone skips inheriting from the ABC, no error at all. Duck typing lets anything through.

## Language Comparison

### PHP — Hot Gravy (native enforcement)
```php
interface ProtocolAdapter {
    public function send(string $text): void;
    public function getChar(string $prompt = ''): string;
}

// Fatal error if close() is missing — compile time, no discussion
class TelnetAdapter implements ProtocolAdapter { ... }
```

### TypeScript — Hot Gravy (compile-time enforcement)
```typescript
interface ProtocolAdapter {
    send(text: string): Promise<void>;
    getChar(prompt?: string): Promise<string>;
    close(): Promise<void>;
}

// Won't compile if any method is missing
class TelnetAdapter implements ProtocolAdapter { ... }
```

### Python — Lukewarm Gravy (ABC, instantiation-time only)
```python
class ProtocolAdapter(ABC):
    @abstractmethod
    async def send(self, text: str): ...

# Only crashes when you try to create an instance, not at import
adapter = BrokenAdapter()  # TypeError: Can't instantiate abstract class
```

### Python — Hotter Gravy (Protocol + mypy)
```python
from typing import Protocol

class ProtocolAdapter(Protocol):
    async def send(self, text: str) -> None: ...
    async def get_char(self, prompt: str = "") -> str: ...
    async def close(self) -> None: ...
    @property
    def term_width(self) -> int: ...
    @property
    def term_height(self) -> int: ...

# mypy catches missing methods at lint time — no inheritance needed
# Any class with the right methods structurally satisfies the Protocol
def start_session(adapter: ProtocolAdapter) -> None:
    ...  # mypy verifies adapter has all required methods
```

**Protocol vs ABC:**
- ABC = nominal typing. You must explicitly inherit. Checked at instantiation.
- Protocol = structural typing. If it has the methods, it satisfies the contract. Checked by mypy at lint time.
- Protocol is closer to how TypeScript interfaces work.
- Protocol doesn't require the implementing class to know about or import the Protocol.

### JavaScript — No Gravy (runtime checks only)
```javascript
// No native interface support. Options:

// 1. Runtime check in factory/constructor
function verifyAdapter(obj) {
    const required = ['send', 'getChar', 'close'];
    const missing = required.filter(m => typeof obj[m] !== 'function');
    if (missing.length) {
        throw new TypeError(`Missing: ${missing.join(', ')}`);
    }
}

// 2. Just use TypeScript instead
```

## Migration Plan for This Project

### Step 1: Python — Switch ABCs to Protocols
Replace `ProtocolAdapter(ABC)` and `ScriptingBackend(ABC)` with `Protocol` classes. Since we already run mypy with zero issues, this makes mypy the enforcer.

```python
# Before (ABC — checks at instantiation)
from abc import ABC, abstractmethod

class ProtocolAdapter(ABC):
    @abstractmethod
    async def send(self, text: str): ...

class TelnetAdapter(ProtocolAdapter):  # must inherit
    async def send(self, text: str): ...

# After (Protocol — checks at lint time via mypy)
from typing import Protocol

class ProtocolAdapter(Protocol):
    async def send(self, text: str) -> None: ...

class TelnetAdapter:  # no inheritance needed — structural match
    async def send(self, text: str) -> None: ...
```

Adapters can drop the `(ProtocolAdapter)` inheritance. mypy verifies structurally.

### Step 2: TypeScript — Already Good
The web frontend uses TypeScript. Add `implements` to adapter classes for explicit enforcement. Vite + tsc catches violations at build time.

### Step 3: Future PHP Backend
When/if we add PHP: use native `interface` keyword. PHP enforces at class load time. No extra tooling needed.

## The Principle

The interface is the decision about where the seam goes. The enforcement is how you keep the seam honest. In a multi-language project:

- **PHP**: language enforces it (fatal error)
- **TypeScript**: compiler enforces it (build error)
- **Python**: mypy enforces it (lint error) — but only if you use Protocol
- **JavaScript**: nothing enforces it — use TypeScript instead

The tighter the enforcement, the more confidently you can hand off implementation to someone else (or an AI). The interface is the leash.
