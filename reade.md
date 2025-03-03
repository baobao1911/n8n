# NGUYEN THAI BAO
## Project Report: Knowledge Base with Self-Learning Mechanism and n8n Integration
### Implementation Details


![upload_index_data](https://github.com/user-attachments/assets/bd631368-98ed-424b-b6a9-d7d375c6ceb1)
**1. Introduction**

This workflow enables users to upload documents (PDF, TXT, Excel) and automatically processes them for indexing. The system orchestrates file retrieval, text extraction, summarization, and embedding creation, all within a single n8n workflow.

**2. Workflow**
   
**node Webhook**: Recieve request from frontend ui when user upload files to store in storage service (Google Drive) and processing and indexing data to load into vector database.

**node Code**: transfom data before storage and processing.

**node Google Drive**: Locates the user’s uploaded files in Google Drive.

**nodes Delete Old File / Delete Old Doc Rows**: Aim to cleanup by removing outdated files or records. Ensures only the latest documents are processed and indexed.

**node Switch**: Routes files to the correct extraction path based on their type. 

For instance:

- Extract File PDF for PDF documents

- Extract File TXT for text files

- Extract File EXCEL for spreadsheets

**node index_encoder**: send processed text to a vector embedding model. This transforms textual content into numerical vectors.

**node mode Embeddings Chunking Data & Recursive Orchestrator Text Splitter**: Splits large texts into smaller chunks before embedding. The Recursive Orchestrator may repeatedly loop until all text is fully processed.

**node Load encoder**: Stores or updates the embeddings in a database or vector store.

![RAG_flow](https://github.com/user-attachments/assets/92d87dbb-356c-402d-9173-5241cc8b23b0)
**1. Introduction**

This architecture ensures that user queries receive real-time, contextually relevant answers enhanced by up-to-date data from the external storage (Postgres, Supabase, or other sources).

**2. Workflow**
**User Query via Webhook**: A request arrives containing a `question`, `user_name`, `session_id`, `Auth token`.

**Store user's value**: Save value of user input.

**create session**: Aim to create new session if user create a new chat session or request from a new user.

***Aggregate & Merge**: Get role from user feedback to make reranking when retrieval data. The user question and the role is combined. This consolidated information is passed along to the AI agent.

**AI Agent (RAG Logic)**: The agent calls the “Retrieve Documents” steps, which use embeddings or vector queries to fetch relevant content from the database. The retrieved text plus user query are fed into the “OpenAI Chat Model.” If there is ongoing conversation context, “Postgres Chat Memory” is updated or read to maintain continuity.

**Generate & Return Answer**: The chat model crafts a final response. The workflow sends this back to the user via the “Respond to Webhook” node.

![get_feedback_and_add_role](https://github.com/user-attachments/assets/3781a187-e1e4-46a6-a1c1-03e1e913ca8a)
**1. Introduction**

This workflow captures user feedback (thumbs up/down) on conversation history, then retrieves and analyzes the relevant chat session to extract key discussion points. An AI model summarizes these points, identifying the user’s main interests or intentions. Finally, the workflow updates the user’s data in the database—specifically, assigning or refining a “role” field based on the conversation insights. This automated process helps maintain a dynamic user profile, ensuring the system adapts to each user’s evolving needs.

**2. Workflow**

**node Webhook**: revice thumb from user with current chat session and history conversation.

**node Query history chat**: This node will get all history chat in this session.

**node AI**: The ai will explain conversation and break down main points of user question. After that ai will generate a query to make reraking in documents.

![image](https://github.com/user-attachments/assets/2c2a47a8-cd67-450e-b27c-655c551d5259)

This's UI of login/ register page. User need to create account before start using service.

![image](https://github.com/user-attachments/assets/be5bcbbe-8eae-4777-8894-71cefb8a34a4)

After login, user had access to main page.

**Left Sidebar**

**User Info & Logout**: Displays the current user’s login status, with a button to log out.

**File Upload Section**: Allows users to drag and drop or browse for files to upload. These files can be ingested by the AI for context or reference.

**Chat Session Management**: Provides options to select an existing chat session or create a new one, then “Activate Session” to begin interacting under that session context.

**Main Panel**

**Documents Dropdown**: A selectable list (labeled “Your documents”) that lets users delete which uploaded documents.

**Chat Window**: Occupies the central area where the conversation with the AI takes place. Users can type their queries or prompts here and send them to the AI, which will respond with context from any activated session and selected documents.

**Search Architecture**: The function combines full‐text and semantic vector searches to rank documents for RAG. It filters documents by metadata, scores them using both text relevance and embedding similarity (via reciprocal rank fusion), and returns the top results. 

Give code bellow: 

```
-- Create a function to search for documents
create or replace function match_documents (
  query_text text,
  query_embedding vector(1536),
  match_count int default null,
  filter jsonb default '{}',
  full_text_weight float default 1,
  semantic_weight float default 1,
  rrf_k int default 50
) 
returns table (
  id bigint,
  content text,
  metadata jsonb,
  similarity float
)
language sql
as $$
with full_text as (
  select
    id,
    row_number() over (order by ts_rank_cd(fts, websearch_to_tsquery(query_text)) desc) as rank_ix
  from documents
  where fts @@ websearch_to_tsquery(query_text)
    and metadata @> filter
  order by rank_ix
  limit least(match_count, 30) * 2
),
semantic as (
  select
    id,
    row_number() over (order by embedding <#> query_embedding) as rank_ix
  from documents
  where metadata @> filter
  order by rank_ix
  limit least(match_count, 30) * 2
)
select 
  d.id,
  d.content,
  d.metadata,
  coalesce(1.0 / (rrf_k + f.rank_ix), 0.0) * full_text_weight +
  coalesce(1.0 / (rrf_k + s.rank_ix), 0.0) * semantic_weight as similarity
from full_text f
full outer join semantic s
  on f.id = s.id
join documents d
  on coalesce(f.id, s.id) = d.id
order by similarity desc
limit least(match_count, 30);
$$; 

```

 
![users](https://github.com/user-attachments/assets/fa903d6f-5067-40b2-914a-2c5b7004dc16)

**Users**: Table to store user's account.

![user_session](https://github.com/user-attachments/assets/d9228389-1e22-4a1c-91cb-9904cbf0be75)

**user_session**: Table to store all session of user.

![user_data](https://github.com/user-attachments/assets/fca7f4dc-934e-4d4c-a7e4-5a9412848176)

**user_data**: table to store role after analysts user feedback. This role aim to rerank document to make better performents.

![chat_history](https://github.com/user-attachments/assets/1305cce9-15d4-4143-a475-8f5cbbe9d440)

**chat_histories**: table to store all conversation of user.

![documents](https://github.com/user-attachments/assets/5fcb5d09-1e88-4ee0-beac-5a887baf06af)

**document**: this table to store all vector docment after processiong and indexing.

---------------------------------------------------------------------------------------------
**Web Interface**

This project ahad deploy on `render` with url: https://n8n-zbra.onrender.com/





