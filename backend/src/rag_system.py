from typing import List, Dict, Any, Optional
import uuid
import json
import os
from datetime import datetime

class RAGSystem:
    """
    Retrieval-Augmented Generation (RAG) system for the NARRA-Gym application.
    
    This is a placeholder implementation. In a real system, this would:
    1. Connect to a vector database (Pinecone/Weaviate)
    2. Store and retrieve story elements, character info, and user data
    3. Provide contextual information for the LLM
    4. Manage long-term memory and context window limitations
    """
    
    def __init__(self):
        # In a real implementation, this would initialize vector DB clients
        self.user_memories = {}  # Map of user_id -> list of memory entries
        self.story_memories = {}  # Map of story_id -> list of story elements
        self.character_memories = {}  # Map of character_id -> character details
        
    def add_user_memory(self, user_id: str, text: str, metadata: Optional[Dict[str, Any]] = None):
        """Add a memory related to the user"""
        if user_id not in self.user_memories:
            self.user_memories[user_id] = []
            
        memory_entry = {
            "id": str(uuid.uuid4()),
            "text": text,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat()
        }
        
        self.user_memories[user_id].append(memory_entry)
        
        # In a real implementation, this would also:
        # 1. Generate embeddings for the text
        # 2. Store the embeddings in the vector DB
        # 3. Associate the embedding with the memory entry
        
        return memory_entry["id"]
    
    def add_story_memory(self, story_id: str, text: str, element_type: str, 
                        metadata: Optional[Dict[str, Any]] = None):
        """Add a memory related to the story (scene, event, etc.)"""
        if story_id not in self.story_memories:
            self.story_memories[story_id] = []
            
        memory_entry = {
            "id": str(uuid.uuid4()),
            "text": text,
            "element_type": element_type,  # e.g., "scene", "dialogue", "event"
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat()
        }
        
        self.story_memories[story_id].append(memory_entry)
        
        # In a real implementation, this would also store embeddings
        
        return memory_entry["id"]
    
    def add_character_memory(self, character_id: str, text: str, relation_to_user: Optional[str] = None,
                           metadata: Optional[Dict[str, Any]] = None):
        """Add a memory related to a character"""
        if character_id not in self.character_memories:
            self.character_memories[character_id] = []
            
        memory_entry = {
            "id": str(uuid.uuid4()),
            "text": text,
            "relation_to_user": relation_to_user,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat()
        }
        
        self.character_memories[character_id].append(memory_entry)
        
        # In a real implementation, this would also store embeddings
        
        return memory_entry["id"]
    
    def retrieve_relevant_context(self, query: str, story_id: Optional[str] = None, 
                                user_id: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context based on a query
        
        In a real implementation, this would:
        1. Generate an embedding for the query
        2. Search the vector DB for similar embeddings
        3. Return the associated memory entries
        """
        # This is a mock implementation that just returns the most recent entries
        results = []
        
        if story_id and story_id in self.story_memories:
            # Get most recent story memories
            story_results = self.story_memories[story_id][-limit:]
            results.extend(story_results)
            
        if user_id and user_id in self.user_memories:
            # Get most recent user memories
            user_results = self.user_memories[user_id][-limit:]
            results.extend(user_results)
            
        # In a real implementation, we would:
        # 1. Sort by relevance (vector similarity)
        # 2. Deduplicate and merge similar information
        # 3. Format the context for the LLM
        
        return results
    
    def generate_story_prompt(self, emotional_need: str, user_id: Optional[str] = None) -> str:
        """
        Generate a prompt for creating a new therapeutic story
        
        This would use the RAG system to create a personalized prompt based on:
        1. The user's emotional need
        2. Any available user information
        3. Therapeutic techniques appropriate for the emotional need
        """
        # Basic prompt template
        prompt = f"""
        Create a therapeutic interactive story to help a person who described their emotional need as:
        "{emotional_need}"
        
        The story should:
        1. Have a protagonist that the user can identify with
        2. Include supportive characters that provide wisdom and perspective
        3. Present situations that parallel the emotional challenge
        4. Offer multiple paths that explore different emotional responses
        5. Lead to insights and emotional growth
        6. End with a sense of resolution and new perspective
        
        Format the response as a structured story beginning with:
        - A title
        - A theme (emotional challenge being addressed)
        - A setting
        - Main characters (including the protagonist representing the user)
        - An opening scene that establishes the situation
        """
        
        # In a real implementation, we would:
        # 1. Retrieve relevant therapeutic techniques for this emotional need
        # 2. Add personalized elements based on user history
        # 3. Include specific guidance based on psychological principles
        
        return prompt
    
    def generate_response_prompt(self, message: str, story_id: str, user_id: str) -> str:
        """
        Generate a prompt for creating a response to the user's message
        
        This would use the RAG system to create a contextual prompt based on:
        1. The story so far
        2. Character information
        3. Therapeutic goals
        4. User's message and emotional state
        """
        # Retrieve relevant context
        context = self.retrieve_relevant_context(message, story_id, user_id)
        context_text = "\n".join([f"- {item['text']}" for item in context])
        
        # Basic prompt template
        prompt = f"""
        You are responding as a character in a therapeutic interactive story.
        
        Context information:
        {context_text}
        
        The user just said:
        "{message}"
        
        Respond in character, while:
        1. Showing empathy and understanding
        2. Guiding the conversation toward therapeutic insights
        3. Maintaining the narrative flow and character consistency
        4. Providing opportunities for the user to explore their feelings
        
        Format the response as dialogue from the character, followed by 2-3 possible choices
        for how the user might respond.
        """
        
        # In a real implementation, we would:
        # 1. Include more specific story and character details
        # 2. Add guidance based on therapeutic techniques
        # 3. Adapt the tone based on the user's emotional state
        
        return prompt

# Example usage (for demonstration)
if __name__ == "__main__":
    rag_system = RAGSystem()
    
    # Add some memories
    user_id = "user123"
    story_id = "story456"
    
    rag_system.add_user_memory(
        user_id, 
        "User is a PhD student in computer science who has had multiple paper rejections",
        {"emotional_state": "discouraged", "confidence": "low"}
    )
    
    rag_system.add_story_memory(
        story_id,
        "The story is set in a university campus during a rainy autumn day",
        "setting",
        {"mood": "contemplative", "time_period": "present day"}
    )
    
    rag_system.add_character_memory(
        "char_mentor",
        "Professor Maya is a wise mentor who has overcome similar challenges in her career",
        "mentor",
        {"personality": "wise, empathetic, encouraging"}
    )
    
    # Generate a prompt
    prompt = rag_system.generate_story_prompt(
        "I'm a CS PhD student, my papers keep getting rejected, and I feel like a failure"
    )
    
    print("Example Story Generation Prompt:")
    print(prompt)
    
    # Generate a response prompt
    response_prompt = rag_system.generate_response_prompt(
        "I don't know if I'm cut out for research anymore",
        story_id,
        user_id
    )
    
    print("\nExample Response Generation Prompt:")
    print(response_prompt) 