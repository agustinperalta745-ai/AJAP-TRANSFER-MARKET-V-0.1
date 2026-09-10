import { Alert } from 'react-native';

import { apiRequest } from './api';

type CycleAction = {
  key: string;
  label: string;
  description: string;
};

type CycleState = {
  phase: string;
  phase_label: string;
  season_number: number;
  competition_id: number | null;
  market_open: boolean;
  next_action: CycleAction;
};

type AdvanceResult = {
  ok: boolean;
  cycle: CycleState;
};

const errorText = (error: unknown) =>
  typeof error === 'object' && error && 'message' in error
    ? String((error as { message?: string }).message)
    : 'No se pudo cambiar la etapa AJPA.';

export async function openCompetitionCycleManagement(
  onUpdated?: (cycle: CycleState) => void | Promise<void>,
): Promise<void> {
  let cycle: CycleState;
  try {
    cycle = await apiRequest<CycleState>('/api/v1/admin/competition-cycle');
  } catch (error) {
    Alert.alert('AJPA', errorText(error));
    return;
  }

  const action = cycle.next_action;
  if (!action?.label) {
    Alert.alert('AJPA', 'No hay una siguiente etapa disponible.');
    return;
  }

  Alert.alert(
    'Gestionar etapa AJPA',
    `Etapa actual: ${cycle.phase_label}\n\nSiguiente acción:\n${action.label}\n\n${action.description}`,
    [
      { text: 'CANCELAR', style: 'cancel' },
      {
        text: 'CONTINUAR',
        onPress: () => {
          Alert.alert(
            'Confirmar cambio de etapa',
            `${action.label}\n\nSe archivarán las estadísticas de la competencia que termina cuando corresponda.\n\nNO se tocan planteles, saldos, fichajes ni historial de clásicos.`,
            [
              { text: 'CANCELAR', style: 'cancel' },
              {
                text: 'CONFIRMAR',
                style: 'destructive',
                onPress: () => {
                  void (async () => {
                    try {
                      const result = await apiRequest<AdvanceResult>(
                        '/api/v1/admin/competition-cycle/advance',
                        {
                          method: 'POST',
                          body: JSON.stringify({ expected_phase: cycle.phase }),
                        },
                      );
                      if (onUpdated) await onUpdated(result.cycle);
                      Alert.alert('Etapa actualizada', `Ahora: ${result.cycle.phase_label}`);
                    } catch (error) {
                      Alert.alert('No se pudo cambiar la etapa', errorText(error));
                    }
                  })();
                },
              },
            ],
          );
        },
      },
    ],
  );
}
