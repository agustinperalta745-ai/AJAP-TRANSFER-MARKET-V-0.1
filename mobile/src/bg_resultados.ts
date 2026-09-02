import { BG_RESULTADOS_PART_0 } from './bg_resultados_part0';
import { BG_RESULTADOS_PART_1 } from './bg_resultados_part1';
import { BG_RESULTADOS_PART_2 } from './bg_resultados_part2';
import { BG_RESULTADOS_PART_3 } from './bg_resultados_part3';

// Fondo local de Resultados. Se mantiene embebido para que la pantalla no dependa
// de una URL externa y conserve la imagen incluso sin conexión.
export const BG_RESULTADOS = `data:image/jpeg;base64,${BG_RESULTADOS_PART_0}${BG_RESULTADOS_PART_1}${BG_RESULTADOS_PART_2}${BG_RESULTADOS_PART_3}`;
