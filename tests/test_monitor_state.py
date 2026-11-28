import unittest
from unittest.mock import Mock, patch

from monitor_state import listar_estado_monitoramento, salvar_estado_monitoramento


class MonitorStateTests(unittest.TestCase):
    @patch("monitor_state.obter_cliente")
    def test_upserts_observation_without_creating_signal(self, get_client):
        response = Mock()
        response.data = [{"provider": "twelvedata", "ativo": "FOREX:EURUSD"}]
        table = Mock()
        table.upsert.return_value.execute.return_value = response
        client = Mock()
        client.table.return_value = table
        get_client.return_value = client

        result = salvar_estado_monitoramento(
            provider="TwelveData",
            ativo="FOREX:EURUSD",
            status="observed",
            sinal_candidato="CALL",
            motivo="Confluência técnica; ainda não é entrada.",
        )

        self.assertEqual(result["ativo"], "FOREX:EURUSD")
        table.upsert.assert_called_once()
        args, kwargs = table.upsert.call_args
        self.assertEqual(kwargs["on_conflict"], "provider,ativo")
        self.assertNotIn("preco_entrada", args[0])
        self.assertNotIn("historico_sinais", str(client.mock_calls))

    @patch("monitor_state.obter_cliente")
    def test_lists_shared_state(self, get_client):
        response = Mock()
        response.data = [{"ativo": "FOREX:EURUSD"}]
        table = Mock()
        table.select.return_value.order.return_value.limit.return_value.execute.return_value = response
        client = Mock()
        client.table.return_value = table
        get_client.return_value = client

        self.assertEqual(listar_estado_monitoramento(), response.data)
        client.table.assert_called_once_with("monitoramento_estado")

    def test_rejects_invalid_status(self):
        with self.assertRaises(ValueError):
            salvar_estado_monitoramento("twelvedata", "EURUSD", "published")

    def test_invalid_candidate_is_downgraded_to_wait(self):
        with patch("monitor_state.obter_cliente") as get_client:
            response = Mock()
            response.data = [{"sinal_candidato": "AGUARDAR"}]
            table = Mock()
            table.upsert.return_value.execute.return_value = response
            client = Mock()
            client.table.return_value = table
            get_client.return_value = client

            salvar_estado_monitoramento(
                "twelvedata", "EURUSD", "observed", "EXECUTAR"
            )
            payload = table.upsert.call_args.args[0]
            self.assertEqual(payload["sinal_candidato"], "AGUARDAR")


if __name__ == "__main__":
    unittest.main()
