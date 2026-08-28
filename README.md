# Coffee Lab

Aplicação web para registrar e explorar o preparo de cafés especiais, reunindo receitas, estoque, extrações, diário sensorial, estatísticas e recursos de IA em um único lugar.

O projeto foi desenvolvido como uma aplicação completa, conectando **frontend, backend, banco de dados, APIs, PWA e Inteligência Artificial**.

## Visão geral

O Coffee Lab nasceu de uma ideia simples: transformar o registro de cada café em um espaço para experimentar, comparar e aprender.

A aplicação permite acompanhar desde o café disponível em estoque até a receita utilizada, os parâmetros de preparo e as percepções sensoriais depois da extração.

## Principais recursos

- Autenticação, perfil e sessão persistente.
- Biblioteca de cafés com busca, filtros, fotos e favoritos.
- Controle de estoque e histórico de movimentações.
- Livro de receitas com etapas, duplicação, compartilhamento e modo guiado.
- Cálculo de café e água a partir do ratio e da quantidade desejada.
- Cronômetro de preparo com registro de extrações.
- Diário sensorial e explorador de perfil sensorial.
- Caderno de bebidas autorais.
- Dashboard com estatísticas e atividade.
- Barista de IA integrado via OpenRouter.
- PWA instalável com recursos offline.
- Cache local e fila para operações realizadas sem conexão.
- Notificações locais.
- Compartilhamento de cafés, receitas, bebidas e extrações em PNG.

## Stack

| Área | Tecnologias |
| --- | --- |
| Backend | Python, FastAPI, SQLAlchemy 2.0, Pydantic 2 |
| Banco de dados | PostgreSQL, NeonDB, Alembic |
| Frontend | HTML5, CSS3, JavaScript Vanilla |
| PWA | Manifest, Service Worker, IndexedDB |
| Visualização | Chart.js |
| Inteligência Artificial | OpenRouter API |
| Desenvolvimento | Git, GitHub, ambiente virtual Python |

## Arquitetura

```text
Coffee Lab
│
├── Backend
│   ├── FastAPI
│   ├── SQLAlchemy
│   ├── Pydantic
│   └── Alembic
│
├── Banco de dados
│   └── PostgreSQL / NeonDB
│
├── Frontend
│   ├── HTML
│   ├── CSS
│   └── JavaScript
│
├── PWA
│   ├── Manifest
│   ├── Service Worker
│   └── IndexedDB
│
└── IA
    └── OpenRouter API
```

## Estrutura principal

```text
.
├── main.py                 # API, rotas e servidor
├── core.py                 # Configurações, banco, modelos e schemas
├── requirements.txt        # Dependências Python
├── alembic.ini             # Configuração Alembic
├── alembic/                # Migrações
├── static/
│   ├── index.html          # Interface principal
│   ├── css/style.css       # Estilos
│   ├── js/app.js           # Lógica da aplicação
│   ├── manifest.json       # Manifest PWA
│   └── icons/              # Ícones
└── sw.js                   # Service Worker
```

## Executando localmente

### 1. Clone o projeto

```bash
git clone https://github.com/vaoliverosdev/coffeeLab.git
cd coffeeLab
```

### 2. Crie o ambiente virtual

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Configure o ambiente

Crie um `.env` na raiz quando quiser utilizar PostgreSQL/NeonDB ou recursos externos:

```env
DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST/DBNAME?sslmode=require
SECRET_KEY=uma-chave-longa-e-segura
OPENROUTER_API_KEY=sua-chave
APP_ENV=development
```

Sem `DATABASE_URL`, o ambiente local pode utilizar SQLite para desenvolvimento.

A chave do OpenRouter só é necessária para o Barista de IA.

Nunca publique chaves ou credenciais no repositório.

### 5. Inicie a aplicação

```bash
uvicorn main:app --reload
```

A aplicação ficará disponível em:

```text
http://localhost:8000
```

Para testar em outro dispositivo da mesma rede:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## PWA e funcionamento offline

O Coffee Lab foi pensado para continuar útil mesmo quando a conexão não está disponível.

A aplicação utiliza:

- App shell em cache.
- Service Worker versionado.
- Navegação offline.
- Persistência local da sessão.
- IndexedDB para dados previamente carregados.
- Fila de operações de escrita realizadas offline.
- Sincronização quando a conexão retorna.
- Proteção contra sincronizações simultâneas.

O Service Worker não intercepta diretamente as rotas de API. O controle de cache e sincronização dos dados da aplicação é feito pela camada de acesso da própria aplicação.

## Banco de dados

O projeto utiliza SQLAlchemy para acesso ao banco e Alembic para evolução controlada do schema.

Comandos úteis:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

## Deploy

O projeto possui configuração para deploy no Render por meio de `render.yaml` e pode utilizar PostgreSQL hospedado no NeonDB.

Em produção, configure as variáveis de ambiente necessárias e utilize uma `SECRET_KEY` segura. Para recursos de e-mail, login social e IA, configure também suas respectivas credenciais no ambiente de deploy.

## Segurança

O projeto inclui validação de senha, verificação de e-mail, recuperação de senha, controle de sessão, limitação de tentativas em rotas sensíveis e validação de uploads.

Credenciais e configurações sensíveis devem permanecer exclusivamente em variáveis de ambiente.

## Status

O Coffee Lab está em desenvolvimento ativo, com foco atual em testes gerais, responsividade, PWA instalado, ajustes de produção, documentação e validação antes de uso intensivo.

## Autor

Victor Oliveros

- GitHub: https://github.com/vaoliverosdev
- LinkedIn: https://www.linkedin.com/in/victor-andres-oliveros-p%C3%A9rez-087035382
