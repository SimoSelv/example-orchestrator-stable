# Guida alla Creazione di un Task Workflow

## Cos'è un Task?

Un **Task** è un tipo speciale di workflow che **non è legato a una subscription specifica** (a differenza dei workflow Create/Modify/Terminate/Validate che operano su un prodotto). I Task vengono usati per operazioni di sistema, manutenzione, o controlli globali.


I Task si trovano nel dropdown **"New task"** della pagina **Tasks** nella UI dell'orchestratore.

---

## Step Necessari

La creazione di un nuovo Task richiede **3 passaggi obbligatori**, ciascuno in un file diverso. Se ne manca anche solo uno, il task non funzionerà o non sarà visibile nella UI.

```
  1️⃣ Codice Python          2️⃣ Registrazione Lazy       3️⃣ Migrazione DB            ✅ Task visibile
  (logica del task)    ──►   (workflows/__init__.py) ──►  (migrations/)          ──►   nella UI
```

---

## Step 1: Creare il File Python del Task

### Dove

```
workflows/tasks/nome_del_task.py
```

### Struttura Base

```python
"""Descrizione del task."""

import structlog
from orchestrator import workflow
from orchestrator.targets import Target
from orchestrator.workflow import StepList, done, init, step
from pydantic_forms.types import State

logger = structlog.get_logger(__name__)


@step("Nome dello step visibile nella UI")
def mio_primo_step() -> State:
    """Docstring che descrive cosa fa questo step."""
    # ... logica ...
    return {"risultato": valore}


@step("Nome del secondo step")
def mio_secondo_step(risultato) -> State:
    """Riceve 'risultato' dallo State del primo step."""
    # ... logica ...
    return {"esito_finale": esito}


@workflow("Nome Visibile nella UI", target=Target.SYSTEM)
def task_nome_del_task() -> StepList:
    return (
        init
        >> mio_primo_step
        >> mio_secondo_step
        >> done
    )
```

### Regole Fondamentali

> [!IMPORTANT]
> - Il decoratore `@workflow` deve avere `target=Target.SYSTEM` per i Task
> - La funzione workflow deve iniziare con il prefisso `task_` per convenzione
> - La catena di step deve iniziare con `init` e terminare con `done`
> - L'operatore `>>` concatena gli step in sequenza

### Come Funziona lo State

Ogni step riceve i suoi parametri dallo **State** (un dizionario condiviso) e restituisce un dizionario che viene **mergiato** nello State per gli step successivi:

```
  {}  ──init──►  {}  ──step_1──►  {nodi: [...]}  ──step_2──►  {nodi: [...], ping: True}  ──done──►  State finale
```

Ad esempio, se il primo step restituisce `{"nodi": lista_nodi}`, il secondo step può ricevere `nodi` come parametro:

```python
@step("Primo step")
def recupera_nodi() -> State:
    nodi = [...]   # logica per recuperare i nodi
    return {"nodi": nodi}   # ← aggiunge 'nodi' allo State


@step("Secondo step")
def analizza_nodi(nodi: list) -> State:  # ← riceve 'nodi' dallo State
    # ... usa la variabile 'nodi' ...
    return {"analisi": risultato}
```

### Riutilizzare Codice Esistente

Prima di scrivere logica da zero, verifica se esistono già funzioni utili in `workflows/shared.py`. Ad esempio:

```python
# ❌ NON reimplementare la query
from orchestrator.db import SubscriptionTable, ProductTable
subs = SubscriptionTable.query.join(ProductTable).filter(...).all()

# ✅ Usare la funzione già esistente
from workflows.shared import subscriptions_by_product_type
from orchestrator.types import SubscriptionLifecycle
subs = subscriptions_by_product_type("Node", [SubscriptionLifecycle.ACTIVE])
```

---

## Step 2: Registrare il Workflow in `__init__.py`

### Dove

```
workflows/__init__.py
```

### Cosa Aggiungere

Aggiungere una riga `LazyWorkflowInstance` in fondo al file:

```python
# In fondo a workflows/__init__.py

LazyWorkflowInstance("workflows.tasks.nome_del_task", "task_nome_del_task")
#                     ↑ percorso Python del modulo       ↑ nome della funzione
```

> [!WARNING]
> - Il **primo argomento** è il percorso Python del modulo (usando `.` come separatore, senza `.py`)
> - Il **secondo argomento** deve corrispondere **esattamente** al nome della funzione decorata con `@workflow` nel file Python creato allo Step 1
> - Se il nome non corrisponde, l'orchestratore non troverà il workflow e si otterrà un errore

### Esempio Concreto

Per un task in `workflows/tasks/check_node_health.py` con funzione `task_check_node_health`:

```python
LazyWorkflowInstance("workflows.tasks.check_node_health", "task_check_node_health")
```

---

## Step 3: Creare la Migrazione Alembic per il Database

Questo è il passaggio più **critico e facile da dimenticare**. Senza la migrazione, il workflow è registrato nel codice Python ma **non esiste nel database**, quindi la UI dell'orchestratore non lo mostra.

### Dove

```
migrations/versions/schema/YYYY-MM-DD_<revision_id>_<descrizione>.py
```

### Come Generare un Revision ID

Serve un identificativo unico per la migrazione. Si può generare con:

```bash
python3 -c "import uuid; print(uuid.uuid4().hex[:12])"
```

### Come Trovare la `down_revision`

La `down_revision` è l'ID della migrazione più recente nella cartella. Ordina i file per data nel nome:

```bash
ls -1 migrations/versions/schema/*.py | sort | tail -1
```

Apri quel file e copia il valore di `revision` — quello sarà il tuo `down_revision`.

### Template della Migrazione

```python
"""Descrizione della migrazione.

Revision ID: <il_tuo_revision_id>
Revises: <down_revision>
Create Date: YYYY-MM-DD HH:MM:SS

"""
import sqlalchemy as sa
from alembic import op
from orchestrator.migrations.helpers import delete_workflow
from orchestrator.targets import Target

# revision identifiers, used by Alembic.
revision = "<il_tuo_revision_id>"
down_revision = "<revision_della_migrazione_precedente>"
branch_labels = None
depends_on = None

tasks = [
    {
        "name": "task_nome_del_task",
        "target": Target.SYSTEM,
        "description": "Nome Visibile nel Dropdown della UI",
        "is_task": True,
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    for task in tasks:
        conn.execute(
            sa.text(
                """INSERT INTO workflows(name, target, description, is_task)
                   VALUES (:name, :target, :description, :is_task)
                   ON CONFLICT DO NOTHING"""
            ),
            task,
        )


def downgrade() -> None:
    conn = op.get_bind()
    for task in tasks:
        delete_workflow(conn, task["name"])
```

> [!CAUTION]
> Il campo `is_task` **deve essere `True`**. Se manca o è `False`, il workflow verrà registrato nel database ma **non comparirà** nel dropdown "New task" della UI. Questo è il campo che la UI usa per filtrare i workflow da mostrare nella sezione Tasks.

### Mapping dei Campi

| Campo nella migrazione | Significato | Dove appare |
|---|---|---|
| `name` | Identificativo interno del workflow | Deve corrispondere al nome usato in `LazyWorkflowInstance` e al nome della funzione Python |
| `target` | Tipo di workflow | `Target.SYSTEM` per i Task |
| `description` | Nome leggibile | Mostrato nel dropdown "New task" della UI |
| `is_task` | Flag task | **Deve essere `True`** per apparire nella sezione Tasks |

---

## Applicazione della Migrazione

La migrazione viene eseguita **automaticamente** al riavvio del container dell'orchestratore. L'entrypoint del container esegue:

```bash
python main.py db upgrade heads
```

Quindi basta riavviare il container:

```bash
docker restart orchestrator
```

Oppure, se si usa `stop.sh` e `run.sh`:

```bash
./stop.sh
./run.sh
```

> [!TIP]
> Per verificare che la migrazione sia stata applicata, si può controllare direttamente il database:
> ```bash
> docker exec postgres psql -U nwa -d orchestrator-core \
>   -c "SELECT name, target, description, is_task FROM workflows WHERE name = 'task_nome_del_task';"
> ```

---

## Checklist Riepilogativa

Prima di considerare il task completo, verificare tutti i punti:

- [ ] **File Python** creato in `workflows/tasks/nome_del_task.py`
  - [ ] Funzione workflow decorata con `@workflow("...", target=Target.SYSTEM)`
  - [ ] Nome funzione con prefisso `task_`
  - [ ] Catena: `init >> step1 >> step2 >> ... >> done`
  - [ ] Ogni step decorato con `@step("Nome visibile")`
  - [ ] Ogni step restituisce un dizionario (`State`)
- [ ] **Registrazione** in `workflows/__init__.py`
  - [ ] `LazyWorkflowInstance("percorso.modulo", "nome_funzione")`
  - [ ] Il nome della funzione corrisponde esattamente
- [ ] **Migrazione Alembic** in `migrations/versions/schema/`
  - [ ] `revision` unico generato
  - [ ] `down_revision` punta alla migrazione precedente
  - [ ] `is_task = True` nel dizionario del task
  - [ ] `ON CONFLICT DO NOTHING` nella query INSERT
  - [ ] Funzione `downgrade()` implementata
- [ ] **Verifica**
  - [ ] Container orchestratore riavviato
  - [ ] Task visibile nel dropdown "New task" della UI
  - [ ] Task eseguibile senza errori

---

## Esempio Completo: "Check Node Health"

Per riferimento, ecco come è stato creato il task `check_node_health` che verifica la raggiungibilità dei nodi di rete.

### File Python (`workflows/tasks/check_node_health.py`)

```python
@workflow("Check Node Health", target=Target.SYSTEM)
def task_check_node_health() -> StepList:
    return (
        init
        >> get_active_nodes        # Recupera tutti i nodi attivi da DB + Netbox
        >> ping_nodes              # Esegue ping ICMP verso ogni nodo
        >> check_ssh_ports         # Verifica porta SSH (22) su ogni nodo
        >> generate_health_report  # Genera il report finale
        >> done
    )
```

**4 step** che eseguono in sequenza:

| Step | Input (dallo State) | Output (aggiunto allo State) |
|---|---|---|
| `get_active_nodes` | - | `nodes`: lista di dict con `device_name`, `mgmt_ip`, `subscription_id` |
| `ping_nodes` | `nodes` | `nodes` arricchiti con `ping_success`, `ping_output` |
| `check_ssh_ports` | `nodes` | `nodes` arricchiti con `ssh_open` |
| `generate_health_report` | `nodes` | `health_reports`: lista di report per nodo |

### Registrazione (`workflows/__init__.py`)

```python
LazyWorkflowInstance("workflows.tasks.check_node_health", "task_check_node_health")
```

### Migrazione (`2026-04-28_72413ade14ea_add_check_node_health_task.py`)

```python
revision = "72413ade14ea"
down_revision = "a87d11eb8dd1"

tasks = [
    {
        "name": "task_check_node_health",
        "target": Target.SYSTEM,
        "description": "Check Node Health",
        "is_task": True,        # ← FONDAMENTALE per la visibilità nella UI
    },
]
```

---

## Errori Comuni e Soluzioni

| Problema | Causa | Soluzione |
|---|---|---|
| Task non visibile nella UI | `is_task` mancante o `False` nella migrazione | Aggiungere `"is_task": True` e riapplicare la migrazione |
| Task non visibile nella UI | Migrazione non creata | Creare il file di migrazione in `migrations/versions/schema/` |
| Task non visibile nella UI | Migrazione non applicata | Riavviare il container orchestratore (`docker restart orchestrator`) |
| Errore all'avvio | Nome funzione non corrisponde in `LazyWorkflowInstance` | Verificare che il secondo argomento sia esattamente il nome della funzione Python |
| Errore "ModuleNotFoundError" | Percorso modulo errato in `LazyWorkflowInstance` | Verificare che il primo argomento corrisponda al percorso del file (usando `.` al posto di `/`, senza `.py`) |
| Step non riceve i dati | Nome parametro non corrisponde alla chiave nello State | Il nome del parametro della funzione deve corrispondere **esattamente** alla chiave restituita dallo step precedente |
| Migrazione Alembic fallisce | `down_revision` errata | Verificare che punti all'ultima migrazione esistente |
