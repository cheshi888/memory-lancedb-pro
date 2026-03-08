# memory-lancedb-pro 用户指南（功能总览 + 安装与使用教程）

本指南面向在低配 VPS（2 核 CPU / 2 GB 内存）及离线/弱网环境下部署和使用 memory-lancedb-pro 的用户。涵盖完整功能清单、安装部署、配置说明、CLI 用法、性能优化与常见问题排查。

---

## 一、功能总览

- 存储与索引
  - LanceDB 后端（本地向量 + FTS/BM25 全文检索）
  - 自动创建表与 FTS 索引，支持 CRUD/统计/批量删除
  - 长上下文分块（chunking），适配大文本嵌入

- 检索与排序（Retrieval Pipeline）
  - 混合检索：向量搜索 + BM25 关键词搜索（融合策略：以向量分为主，BM25 命中给予加成）
  - Rerank 重排模式（可选）
    - cross-encoder（云端 API：Jina/SiliconFlow/Voyage/Pinecone）
    - local-cross-encoder（本地小型交叉编码器，@xenova/transformers，离线）
    - lightweight（仅余弦相似度，完全离线）
    - none（不重排）
  - 多层评分/过滤
    - 时效加成（Recency Boost）
    - 重要性加权（Importance Weight）
    - 长度归一化（防止长文本“凭密度称王”）
    - 时间衰减（Time Decay，带强化调整）
    - 硬最低分阈值（Hard Min Score）
    - MMR 多样性去重（防止几乎重复的结果占满 Top-K）
    - 噪声过滤（拒绝回复/Meta 问题/寒暄剔除）

- 嵌入（Embedding）
  - OpenAI 兼容任意提供商（OpenAI、Jina、Gemini、Ollama 本地等）
  - 本地微模型（@xenova/transformers）完全离线
  - Task-aware Embedding（可选 taskQuery/taskPassage）
  - 维度可显式覆盖（适配自定义模型）

- 模式与隔离
  - 多 Scope 隔离（global/agent:xxx/custom:xxx/project:xxx/user:xxx）
  - Agent 级访问控制（仅允许特定 Agent 访问指定 Scope）

- 自适应检索与自动化
  - 自适应检索（跳过问候/短命令等无检索价值输入）
  - 自动捕获（Auto-Capture）与自动回忆（Auto-Recall，默认关闭）
  - Session 记忆（/new 钩子，默认关闭）
  - 访问强化（Access Reinforcement）：频繁手动 recall 的记忆衰减更慢

- CLI 与管理
  - 完整 CLI：list/search/stats/delete/delete-bulk/export/import/reembed/migrate
  - 管理工具（memory_list / memory_stats）可选启用
  - 从内置 memory-lancedb 迁移（检查/执行/验证）

- 其他
  - 可选 Markdown 镜像（mdMirror：双写至人类可读的 .md 文件）
  - 大量 UI 提示（openclaw.plugin.json → uiHints）
  - 纯离线工作流（不配置 API Key 自动降级本地、离线重排）

---

## 二、系统需求与准备

- Node.js 18+（建议）
- 已安装 OpenClaw（具备 openclaw CLI）
- 可写的 OpenClaw workspace 目录（默认：~/.openclaw/workspace）
- 首次使用本地模型时需联网下载权重（完成后可全离线）
- Windows 用户注意 PowerShell 执行策略（建议使用 cmd 或调整执行策略）

检查 OpenClaw 基础配置（非必须，但推荐执行并记录真实输出）：
```
openclaw config get agents.defaults.workspace
openclaw config get plugins.load.paths
openclaw config get plugins.slots.memory
openclaw config get plugins.entries.memory-lancedb-pro
```

---

## 三、安装与启用

你可以选择将插件放在 OpenClaw workspace 的 plugins 目录，或写绝对路径。推荐方案 A。

### 方案 A（推荐）：安装到 workspace/plugins/

1）切换到你的 OpenClaw workspace（以实际输出为准）
```
cd /path/to/your/openclaw/workspace
```

2）克隆插件到 workspace/plugins/
```
git clone https://github.com/win4r/memory-lancedb-pro.git plugins/memory-lancedb-pro
```

3）安装依赖
```
cd plugins/memory-lancedb-pro
npm install
```

4）在 OpenClaw 配置（openclaw.json）中加入路径，并启用插件与内存槽
```
{
  "plugins": {
    "load": { "paths": ["plugins/memory-lancedb-pro"] },
    "entries": {
      "memory-lancedb-pro": {
        "enabled": true,
        "config": { ...见“配置示例”... }
      }
    },
    "slots": { "memory": "memory-lancedb-pro" }
  }
}
```

5）清理 jiti 缓存并重启（必须）
- Linux/macOS（通常在 /tmp/jiti/）
```
rm -rf /tmp/jiti/
openclaw gateway restart
```
- Windows（建议清理系统临时目录下 jiti 缓存；若不确定路径，可重启系统服务进程或参考 OpenClaw 文档）
- 配置项变更无需清缓存；修改 .ts 代码必须清 jiti 缓存

### 方案 B：任意目录 + 绝对路径

如果不在 workspace/plugins/ 下，请在 openclaw.json 中写绝对路径：
```
{
  "plugins": {
    "load": {
      "paths": ["/absolute/path/to/memory-lancedb-pro"]
    }
  }
}
```

---

## 四、快速启动（2C/2G VPS 离线最小配置）

无需任何 API Key，即可纯离线运行（首次联网下载权重后完全离线）：
```
{
  "plugins": {
    "entries": {
      "memory-lancedb-pro": {
        "enabled": true,
        "config": {
          "embedding": {
            "provider": "local",
            "model": "all-MiniLM-L6-v2",
            "normalized": true,
            "chunking": true
          },
          "retrieval": { "rerank": "lightweight" },
          "autoRecall": false
        }
      }
    },
    "slots": { "memory": "memory-lancedb-pro" }
  }
}
```

可选：启用本地交叉编码器重排（仍离线）
- Linux/macOS:
```
export LOCAL_RERANK=1
export RERANK_LOCAL_MODEL="Xenova/cross-encoder-ms-marco-MiniLM-L-6-v2" # 可选
```
- Windows PowerShell:
```
$env:LOCAL_RERANK = "1"
$env:RERANK_LOCAL_MODEL = "Xenova/cross-encoder-ms-marco-MiniLM-L-6-v2"
```
未设置 LOCAL_RERANK 时，默认使用 lightweight（仅余弦）更省资源。

重启并预热一次（首次会下载本地模型权重）：
```
openclaw gateway restart
```

---

## 五、进阶配置（完整字段说明）

以下为典型配置片段（仅示意，字段请以 openclaw.plugin.json 的 configSchema 为准）：
```
{
  "embedding": {
    "provider": "openai-compatible" | "local",
    "apiKey": "${JINA_API_KEY}" | ["key1","key2"],  // local 时可不填
    "model": "jina-embeddings-v5-text-small" | "all-MiniLM-L6-v2" | "text-embedding-3-small" | "gemini-embedding-001" | "nomic-embed-text",
    "baseURL": "https://api.jina.ai/v1" | "https://api.openai.com/v1" | "https://generativelanguage.googleapis.com/v1beta/openai/" | "http://localhost:11434/v1",
    "dimensions": 1024 | 384 | 1536 | 3072,         // 可覆盖
    "taskQuery": "retrieval.query",
    "taskPassage": "retrieval.passage",
    "normalized": true,
    "chunking": true
  },
  "dbPath": "~/.openclaw/memory/lancedb-pro",
  "autoCapture": true,
  "autoRecall": false,
  "retrieval": {
    "mode": "hybrid" | "vector",
    "vectorWeight": 0.7,
    "bm25Weight": 0.3,
    "minScore": 0.3,
    "rerank": "cross-encoder" | "local-cross-encoder" | "lightweight" | "none",
    "rerankApiKey": "${JINA_API_KEY}",              // cross-encoder 时需要
    "rerankModel": "jina-reranker-v3",
    "rerankEndpoint": "https://api.jina.ai/v1/rerank",
    "rerankProvider": "jina" | "siliconflow" | "voyage" | "pinecone",
    "candidatePoolSize": 20,
    "recencyHalfLifeDays": 14,
    "recencyWeight": 0.1,
    "filterNoise": true,
    "lengthNormAnchor": 500,
    "hardMinScore": 0.35,
    "timeDecayHalfLifeDays": 60,
    "reinforcementFactor": 0.5,
    "maxHalfLifeMultiplier": 3
  },
  "enableManagementTools": false,
  "scopes": {
    "default": "global",
    "definitions": {
      "global": { "description": "共享知识库" },
      "agent:discord-bot": { "description": "Discord 机器人私有" }
    },
    "agentAccess": {
      "discord-bot": ["global", "agent:discord-bot"]
    }
  },
  "sessionMemory": {
    "enabled": false,
    "messageCount": 15
  },
  "mdMirror": {
    "enabled": false,
    "dir": "/path/to/fallback/dir"
  }
}
```

重要说明：
- 未提供 embedding.apiKey（且未设置 OPENAI_API_KEY）时，即使 provider = "openai-compatible"，也会自动降级为本地模式（provider:"local" + model:"all-MiniLM-L6-v2"）。此时 rerank 默认为 lightweight（除非设置了 LOCAL_RERANK 或提供了 rerankApiKey）。
- 2C/2G 环境建议：
  - rerank: "lightweight"（最省）
  - candidatePoolSize 20 或更低
  - autoRecall: false（减少 token）
  - 保持 @xenova/transformers 的线程为 1–2（代码已限制）

---

## 六、验证与日常操作

验证插件安装/加载：
```
openclaw plugins list
openclaw plugins info memory-lancedb-pro
openclaw plugins doctor
openclaw config get plugins.slots.memory   # 期望 "memory-lancedb-pro"
```

CLI（在任意能访问该插件环境的终端执行）：
```
# 版本
openclaw memory-pro version

# 列表/搜索/统计
openclaw memory-pro list [--scope global] [--category fact] [--limit 20] [--json]
openclaw memory-pro search "query" [--scope global] [--limit 10] [--json]
openclaw memory-pro stats [--scope global] [--json]

# 删除（单个/批量）
openclaw memory-pro delete <id>           # 支持 8+ 字符前缀
openclaw memory-pro delete-bulk --scope global [--before 2025-01-01] [--dry-run]

# 导出/导入
openclaw memory-pro export [--scope global] [--output memories.json]
openclaw memory-pro import memories.json [--scope global] [--dry-run]

# 重新嵌入（切换模型后）
openclaw memory-pro reembed --source-db /path/to/old-db [--batch-size 32] [--skip-existing]

# 迁移（从内置 memory-lancedb）
openclaw memory-pro migrate check [--source /path]
openclaw memory-pro migrate run   [--source /path] [--dry-run] [--skip-existing]
openclaw memory-pro migrate verify[--source /path]
```

---

## 七、最佳实践与性能优化（2C/2G）

- 首次“预热”：在低峰期执行一次检索/导入，完成模型权重下载并缓存后再转为离线。
- 嵌入/重排线程：@xenova/transformers 已限制为 1–2 线程，批量处理串行化，避免 OOM。
- 检索参数：
  - 减小 candidatePoolSize（如 20）
  - rerank 选 "lightweight" 或按需用 LOCAL_RERANK 启用本地 CE
- 减少无意义检索：确保 autoRecall: false；利用自适应检索避免短 query 触发检索。
- 数据卫生：保持记忆短小、原子化（< 500 字符），避免冗长摘要污染；适当使用类别和 scope。

---

## 八、与内置 memory-lancedb 的差异与迁移

- 增强项：BM25/混合融合/重排/多重评分管线/多 Scope/自适应检索/噪声过滤/管理 CLI/访问强化等。
- 迁移步骤：
  1. 停止旧插件（或不再在 memory 槽指向内置插件）
  2. 使用 migrate check/run/verify 从旧库迁入
  3. 必要时执行 reembed 以统一新模型维度与质量
  4. 验证 list/search/stats

---

## 九、常见问题 / 排错

- Windows PowerShell 执行策略阻止 npm.ps1
  - 现象：运行 npm 报“因系统禁止运行脚本…Execution_Policies”
  - 解决：使用 cmd 执行（cmd /d /c "npm install && npm test"），或更改执行策略（管理员 PowerShell：Set-ExecutionPolicy RemoteSigned）

- LanceDB / Apache Arrow “Cannot mix BigInt and other types”
  - 请升级 memory-lancedb-pro 至 >= 1.0.14，插件已在分数/时间字段处做 Number() 统一转换

- 嵌入维度不匹配
  - 切换模型后，显式设置 embedding.dimensions 与实际输出一致；必要时 reembed

- 本地模型下载失败或过慢
  - 首次使用需联网下载权重；建议预热时段执行或预置缓存（@xenova/transformers 默认缓存目录按平台而定）

- 自动回忆导致对话泄漏记忆片段
  - 建议关闭 autoRecall，或在 Agent system prompt 中要求“不得在回复中展示 <relevant-memories> 内容，只可内部参考”

---

## 十、安全与运维建议

- API Key 不要写入仓库；推荐使用环境变量（并确保 Gateway 服务进程环境中可见）
- 修改 .ts 源码后必须清理 jiti 缓存再重启，否则加载旧代码
- 合理规划 scope：通用规则/偏好/坑 → global；Agent 私有 → agent:<id>
- 高频使用的记忆可受“访问强化”影响而衰减更慢（仅 manual 源触发）

---

## 十一、附录：推荐配置片段

1）离线最小配置（2C/2G）
```
{
  "embedding": {
    "provider": "local",
    "model": "all-MiniLM-L6-v2",
    "normalized": true,
    "chunking": true
  },
  "retrieval": { "rerank": "lightweight" },
  "autoRecall": false
}
```

2）Jina（Embedding + Rerank）
```
{
  "embedding": {
    "provider": "openai-compatible",
    "apiKey": "${JINA_API_KEY}",
    "model": "jina-embeddings-v5-text-small",
    "baseURL": "https://api.jina.ai/v1",
    "dimensions": 1024,
    "taskQuery": "retrieval.query",
    "taskPassage": "retrieval.passage",
    "normalized": true
  },
  "retrieval": {
    "rerank": "cross-encoder",
    "rerankApiKey": "${JINA_API_KEY}",
    "rerankModel": "jina-reranker-v3"
  }
}
```

3）Ollama 本地嵌入（需本机 11434 端口）
```
{
  "embedding": {
    "provider": "openai-compatible",
    "baseURL": "http://localhost:11434/v1",
    "model": "nomic-embed-text",
    "dimensions": 768
  },
  "retrieval": { "rerank": "lightweight" }
}
```

---

如需英文版说明，请参考仓库 README.md。若需进一步定制（多机部署、冷热分层、跨项目路由、数据脱敏），可在 Issues 或讨论区提出需求。
