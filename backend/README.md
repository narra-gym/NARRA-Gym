# NARRA-Gym Backend

This is the backend service for the NARRA-Gym emotional healing interactive story application.

## Overview

The backend handles:

1. User data management
2. Story generation using LLM APIs
3. RAG system for context management
4. Media file processing

## Architecture

The backend is designed with:

- FastAPI for the REST API endpoints
- Vector database (Pinecone/Weaviate) for RAG
- Integration with OpenAI/Claude APIs
- PostgreSQL for relational data storage

## Future Implementation

The backend will include:
- User authentication
- Conversation history management
- Prompt engineering for therapeutic storytelling
- Semantic search capabilities
- Personal data integration
- Multi-modal support for image processing 

## 环境变量配置

在项目根目录创建一个 `.env` 文件，包含以下配置项：

```
# 统一 LLM 配置
LLM_PROVIDER=openai
LLM_API_KEY=your_api_key_here

# 可选：覆盖 provider 默认地址
# OpenAI 默认是 https://api.openai.com/v1
# OpenRouter 默认是 https://openrouter.ai/api/v1
# LLM_BASE_URL=

# 按任务分配模型
LLM_DEFAULT_MODEL=gpt-5.4-mini
LLM_STORY_MODEL=gpt-5.4
LLM_INTERACTIVE_ELEMENT_MODEL=gpt-5.4
LLM_QUESTIONS_MODEL=gpt-5.4-mini
LLM_KEYWORDS_MODEL=gpt-5.4-mini
LLM_PROFILE_KEYWORDS_MODEL=gpt-5.4-mini
LLM_REFLECTION_MODEL=gpt-5.4

# 对不支持 temperature 的模型做白名单控制
LLM_TEMPERATURELESS_MODELS=gpt-5.4,gpt-5.4-mini,gpt-5
```

如果要切到 OpenRouter：

```
LLM_PROVIDER=openrouter
LLM_API_KEY=your_openrouter_api_key_here
LLM_DEFAULT_MODEL=openai/gpt-5.4-mini
LLM_STORY_MODEL=openai/gpt-5.4
LLM_INTERACTIVE_ELEMENT_MODEL=openai/gpt-5.4
LLM_QUESTIONS_MODEL=openai/gpt-5.4-mini
LLM_KEYWORDS_MODEL=openai/gpt-5.4-mini
LLM_PROFILE_KEYWORDS_MODEL=openai/gpt-5.4-mini
LLM_REFLECTION_MODEL=openai/gpt-5.4
OPENROUTER_APP_NAME=NARRA-Gym
# 可选
# OPENROUTER_SITE_URL=https://your-site.example.com
```

说明：
- 现在推荐只使用 `LLM_*` 这组统一配置。
- 老的 `OPENAI_API_KEY`、`OPENAI_MODEL`、`STORY_MODEL` 等字段仍然兼容，但更建议逐步迁移。
- 对于 `gpt-5.4`、`gpt-5.4-mini`、`gpt-5` 这类不支持 `temperature` 的模型，系统会自动跳过该参数。

## Benchmark Mode

后端现在支持实验模式、条件分配、数据库化日志和数据导出。

建议增加这些环境变量：

```
EXPERIMENT_DB_PATH=data/emobenchmark.sqlite3
EXPORT_OUTPUT_DIR=exports
```

可选：通过 `EXPERIMENT_CONDITIONS_JSON` 预置 benchmark 条件。每个 condition 都可以覆盖不同任务的模型，例如：

```json
[
  {
    "id": "baseline",
    "name": "Baseline",
    "active": true,
    "llm_config": {
      "default": "gpt-5.4-mini",
      "story": "gpt-5.4",
      "interactive_element": "gpt-5.4",
      "questions": "gpt-5.4-mini",
      "keywords": "gpt-5.4-mini",
      "profile_keywords": "gpt-5.4-mini",
      "reflection": "gpt-5.4"
    }
  }
]
```

可用接口：
- `POST /experiments/session/start`：创建受试者 session 并自动分配 condition
- `GET /experiments/conditions`：查看当前可用 condition
- `GET /experiments/export`：导出 JSON 数据
- `GET /experiments/export?format=csv&table=turn_logs`：导出指定表 CSV

当前会持久化：
- participants
- experiment_conditions
- experiment_sessions
- story_events
- turn_logs
- feedback_logs

## 分步骤故事生成

系统支持分步骤生成故事，共分为5个步骤：

1. **基础框架**：生成故事的标题、高概念前提、主题和情感基调
2. **世界构建**：生成故事的设定和环境
3. **角色创建**：生成故事中的角色
4. **故事结构**：生成故事的分幕结构
5. **开场和互动元素**：生成故事的开场序列、初始对话、分支选择和隐藏元素

每个步骤都有相应的API端点：

```
POST /story/create/step1 - 基础框架
POST /story/create/step2 - 世界构建
POST /story/create/step3 - 角色创建
POST /story/create/step4 - 故事结构
POST /story/create/step5 - 开场和互动元素
GET /story/progress/{story_id} - 获取故事生成进度
POST /story/complete/{story_id} - 完成故事生成并返回完整数据
```

分步骤生成的优势：
- 更精细地控制每个部分的生成质量
- 减轻单次请求的复杂度
- 用户可以在步骤之间进行修改和调整
- 提供进度反馈，改善用户体验

python -m uvicorn src.main:app --reload
