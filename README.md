# Demo de palco — MVP Conf (orquestração de agentes)

Demo animada para a palestra de **Glaucio Daniel** (Hcode / Microsoft MVP): um comando de voz dispara um pipeline multiagente (Handoff → Swarm → Magentic → Group Chat → Swarm de imagens) e termina na proposta **Hcode Training**.

## Subir

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Sem Azure (recomendado no ensaio / se credenciais faltarem):
python run.py --mock

# Com Microsoft Foundry (az login + .env):
cp .env.example .env
# edite AZURE_AI_PROJECT_ENDPOINT e as implantações
az login
python run.py
```

Abre `http://127.0.0.1:8765/`.

## Configuração Azure

1. Copie `.env.example` → `.env`.
2. Preencha o endpoint do projeto Foundry e os nomes das implantações:
   - `AZURE_DEPLOYMENT_FAST` — todos os agentes (exceto Redator)
   - `AZURE_DEPLOYMENT_STRONG` — Redator
   - `AZURE_DEPLOYMENT_IMAGE` — imagens (opcional; há fallback SVG)
   - `AZURE_DEPLOYMENT_TRANSCRIBE` — voz no backend (opcional)
3. Autenticação: `az login` (`DefaultAzureCredential` / `AzureCliCredential`). Sem chave no `.env`.

Pacotes: `agent-framework` (≥1.26) + `agent-framework-orchestrations`. Agentes via `Agent` + `OpenAIChatClient(azure_endpoint=…, credential=…)` (os nomes antigos `ChatAgent` / `AzureAIAgentClient` mudaram). Builders: `SequentialBuilder`, `ConcurrentBuilder`, `HandoffBuilder`, `GroupChatBuilder`, `MagenticBuilder`. Se a API divergir, o pipeline faz fallback instrumentado e registra no log — a UI continua mostrando os cinco padrões.

## Warmup de pesquisa

```bash
python run.py --warmup "Contoso"
```

Salva em `data/cache/<empresa>.json`. Ao vivo, pesquisadores usam o cache; a web só complementa.

## Atalhos

| Atalho | Ação |
|--------|------|
| **Espaço** (segurar) | Gravar voz |
| **Enter** no campo | Disparar pipeline |
| **R** | Replay do último run / golden |
| **Shift+R** | Marcar execução atual como `runs/golden.json` |

Voz: Web Speech (Chrome) → backend Foundry/faster-whisper → caixa de texto.

## Logo Hcode Training

Já em `assets/brand/`:

- `hcode-training-color.png` — tela final da proposta (fundo branco)
- `hcode-training-white.png` — marca no topo do palco (tema navy MVP Conf)

## Checklist de palco

- [ ] Rodar **3×** com `python run.py --measure` (ou `--mock`) e cronometrar (&lt; 3 min)
- [ ] Gravar replay oficial (**Shift+R**) e testar **R** com Wi‑Fi desligado
- [ ] Gravar vídeo da tela (plano C)
- [ ] Testar microfone do local + Web Speech
- [ ] Conferir cotas no Azure (se modo real)
- [ ] Ajustar zoom do navegador para o projetor (1920×1080 / 1280×720)
- [ ] Conferir logo em `assets/brand/`

## Estrutura

- `app/` — FastAPI, WebSocket, pipeline, agentes, serviços
- `static/` — página única (grafo Canvas + proposta)
- `runs/` — eventos de cada execução (replay)
- `data/cache/` — pesquisa pré-aquecida
- `assets/fallback/` — imagens de reserva
- `config.json` — orçamentos de tempo e tokens
