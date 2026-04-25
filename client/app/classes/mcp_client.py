import os
import asyncio
from mcp import ClientSession, Resource, StdioServerParameters, Tool
from mcp.types import Prompt, CallToolResult, ReadResourceResult, GetPromptResult
from mcp.client.stdio import stdio_client          
from mcp.client.sse import sse_client               
from contextlib import AsyncExitStack
from app.utils.logger import logger

class McpClient:
    def __init__(self): 
        self.server_params: StdioServerParameters = None  
        self.session: ClientSession = None                
        self.exit_stack = AsyncExitStack()

    async def initialize_with_stdio(self, command: str, args: list):
        logger.debug("Iniciando conexão MCP via stdio: command=%s args=%s", command, args)
        self.server_params = StdioServerParameters(
            command=command,
            args=args,
        )
        self.client = await self.exit_stack.enter_async_context(stdio_client(self.server_params))
        read, write = self.client
        self.session = await self.exit_stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        logger.info("Sessão MCP stdio inicializada com sucesso")

    async def initialize_with_http(self, host: str):
        """Initialize connection using SSE/HTTP transport."""
        logger.debug("Iniciando conexão MCP via SSE/HTTP: host=%s", host)
        self.client = await self.exit_stack.enter_async_context(sse_client(host))
        read, write = self.client
        self.session = await self.exit_stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        logger.info("Sessão MCP HTTP inicializada com sucesso: host=%s", host)

    async def get_tools(self) -> list[Tool]:
        response = await self.session.list_tools()
        logger.debug("Ferramentas disponíveis: %s", [t.name for t in response.tools])
        return response.tools

    async def get_resources(self) -> list[Resource]:
        response = await self.session.list_resources()
        logger.debug("Recursos disponíveis: %s", [r.uri for r in response.resources])
        return response.resources

    async def get_prompts(self) -> list[Prompt]:
        response = await self.session.list_prompts()
        logger.debug("Prompts disponíveis: %s", [p.name for p in response.prompts])
        return response.prompts

    async def call_tool(self, tool_name: str, args: dict[str, object]) -> CallToolResult:
        logger.info("Chamando ferramenta: %s | args=%s", tool_name, args)
        try:
            result = await self.session.call_tool(tool_name, arguments=args)
            logger.debug("Ferramenta '%s' retornou com sucesso", tool_name)
            return result
        except Exception as exc:
            logger.error("Erro ao chamar ferramenta '%s': %s", tool_name, exc)
            raise

    async def get_resource(self, uri: str) -> ReadResourceResult:
        logger.debug("Lendo recurso: %s", uri)
        return await self.session.read_resource(uri)

    async def invoke_prompt(self, prompt_name: str, args) -> GetPromptResult:
        logger.info("Invocando prompt: %s | args=%s", prompt_name, args)
        return await self.session.get_prompt(prompt_name, arguments=args)

    def format_tools_llm(self, tools) -> list[object]:
        formatted_tools = []
        for tool in tools:
            formatted_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                }
            })
        return formatted_tools

    async def cleanup(self) -> None:
        logger.info("Encerrando sessão MCP e liberando recursos")
        await self.exit_stack.aclose()