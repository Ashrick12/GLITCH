from pygls.server import LanguageServer
from lsprotocol.types import (TEXT_DOCUMENT_DID_OPEN, TEXT_DOCUMENT_DID_CLOSE,
                              TEXT_DOCUMENT_DID_CHANGE)
from lsprotocol.types import (DidOpenTextDocumentParams,
                              DidCloseTextDocumentParams,
                              DidChangeTextDocumentParams)

language_server = LanguageServer('glitch', 'v0.1')


@language_server.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: LanguageServer, params: DidOpenTextDocumentParams):
    ls.show_message('Opened Document')


@language_server.feature(TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls: LanguageServer, params: DidCloseTextDocumentParams):
    ls.show_message('Closed Document')


@language_server.feature(TEXT_DOCUMENT_DID_OPEN)
def did_change(ls: LanguageServer, params: DidChangeTextDocumentParams):
    ls.show_message('Changed Document')
