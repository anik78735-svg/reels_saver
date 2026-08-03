"""
MCP (Model Context Protocol) Server
"""

import json
import asyncio
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from .tools import DownloadTools

@dataclass
class MCPRequest:
    """MCP Request"""
    method: str
    params: Dict[str, Any]
    id: Optional[int] = None

@dataclass
class MCPResponse:
    """MCP Response"""
    result: Dict[str, Any]
    id: Optional[int] = None
    error: Optional[Dict[str, Any]] = None

class MCPServer:
    """
    MCP (Model Context Protocol) Server
    
    This server exposes social media download functionality to AI models
    through the Model Context Protocol.
    
    Usage:
        server = MCPServer()
        server.register_tools()
        response = await server.handle_request(request)
    """
    
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.tool_descriptions: Dict[str, Dict[str, Any]] = {}
        self._register_default_tools()
    
    def _register_default_tools(self):
        """Register default tools"""
        self.register_tool(
            name='download_video',
            description='Download a video from social media platforms',
            handler=DownloadTools.download_video,
            parameters={
                'url': {'type': 'string', 'description': 'URL of the video'},
                'save_to': {'type': 'string', 'description': 'Where to save (local, gallery, drive)', 'default': 'local'}
            }
        )
        
        self.register_tool(
            name='preview_video',
            description='Get preview information for a video',
            handler=DownloadTools.preview_video,
            parameters={
                'url': {'type': 'string', 'description': 'URL of the video'}
            }
        )
        
        self.register_tool(
            name='bulk_download',
            description='Download multiple videos at once',
            handler=DownloadTools.bulk_download,
            parameters={
                'urls': {'type': 'array', 'description': 'List of video URLs'},
                'save_to': {'type': 'string', 'description': 'Where to save', 'default': 'local'}
            }
        )
        
        self.register_tool(
            name='get_supported_platforms',
            description='Get list of supported social media platforms',
            handler=DownloadTools.get_supported_platforms,
            parameters={}
        )
    
    def register_tool(
        self,
        name: str,
        description: str,
        handler: Callable,
        parameters: Dict[str, Any]
    ):
        """
        Register a tool with the MCP server
        
        Args:
            name: Tool name
            description: Tool description
            handler: Function to call
            parameters: Parameter schema
        """
        self.tools[name] = handler
        self.tool_descriptions[name] = {
            'description': description,
            'parameters': parameters
        }
    
    def get_tools_list(self) -> List[Dict[str, Any]]:
        """
        Get list of available tools
        
        Returns:
            List of tool descriptions
        """
        return [
            {
                'name': name,
                'description': info['description'],
                'parameters': info['parameters']
            }
            for name, info in self.tool_descriptions.items()
        ]
    
    async def handle_request(self, request: MCPRequest) -> MCPResponse:
        """
        Handle an MCP request
        
        Args:
            request: MCP request
            
        Returns:
            MCP response
        """
        try:
            method = request.method
            
            if method == 'tools/list':
                return MCPResponse(
                    result={'tools': self.get_tools_list()},
                    id=request.id
                )
            
            elif method == 'tools/call':
                tool_name = request.params.get('name')
                arguments = request.params.get('arguments', {})
                
                if tool_name not in self.tools:
                    return MCPResponse(
                        error={
                            'code': -32601,
                            'message': f'Tool not found: {tool_name}'
                        },
                        id=request.id
                    )
                
                # Execute the tool
                handler = self.tools[tool_name]
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(**arguments)
                else:
                    result = handler(**arguments)
                
                return MCPResponse(
                    result={'output': result},
                    id=request.id
                )
            
            else:
                return MCPResponse(
                    error={
                        'code': -32601,
                        'message': f'Method not found: {method}'
                    },
                    id=request.id
                )
                
        except Exception as e:
            return MCPResponse(
                error={
                    'code': -32603,
                    'message': str(e)
                },
                id=request.id if request else None
            )
    
    def serve(self, host: str = '0.0.0.0', port: int = 8080):
        """
        Start MCP server (HTTP)
        
        Args:
            host: Server host
            port: Server port
        """
        from flask import Flask, request, jsonify
        
        app = Flask(__name__)
        
        @app.route('/mcp', methods=['POST'])
        async def mcp_endpoint():
            data = request.get_json()
            req = MCPRequest(
                method=data.get('method'),
                params=data.get('params', {}),
                id=data.get('id')
            )
            response = await self.handle_request(req)
            return jsonify({
                'jsonrpc': '2.0',
                'result': response.result if response.result else None,
                'error': response.error,
                'id': response.id
            })
        
        @app.route('/mcp/tools', methods=['GET'])
        def tools_endpoint():
            return jsonify({'tools': self.get_tools_list()})
        
        print(f"🚀 MCP Server running on http://{host}:{port}")
        app.run(host=host, port=port)
    
    def serve_stdio(self):
        """
        Start MCP server over stdio (for AI model integration)
        """
        import sys
        
        def log(msg):
            sys.stderr.write(f"{msg}\n")
            sys.stderr.flush()
        
        log("🚀 MCP Server started (stdio mode)")
        
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                
                data = json.loads(line)
                req = MCPRequest(
                    method=data.get('method'),
                    params=data.get('params', {}),
                    id=data.get('id')
                )
                
                # Run async handler
                response = asyncio.run(self.handle_request(req))
                
                result = {
                    'jsonrpc': '2.0',
                    'id': response.id
                }
                if response.error:
                    result['error'] = response.error
                else:
                    result['result'] = response.result
                
                sys.stdout.write(json.dumps(result) + '\n')
                sys.stdout.flush()
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                log(f"Error: {e}")
                break
