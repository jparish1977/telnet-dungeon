/**
 * Terminal-style text renderer on canvas.
 * Renders server ANSI text output as colored monospace text.
 * This is the "cheesedick" renderer — a terminal emulator in canvas.
 * Three.js 3D renderer will come later.
 */

const ANSI_COLORS: Record<string, string> = {
    '30': '#000000', '31': '#cc0000', '32': '#00cc00', '33': '#cccc00',
    '34': '#0000cc', '35': '#cc00cc', '36': '#00cccc', '37': '#cccccc',
    '90': '#666666', '91': '#ff3333', '92': '#33ff33', '93': '#ffff33',
    '94': '#3333ff', '95': '#ff33ff', '96': '#33ffff', '97': '#ffffff',
};

const ANSI_BG_COLORS: Record<string, string> = {
    '40': '#000000', '41': '#cc0000', '42': '#00cc00', '43': '#cccc00',
    '44': '#0000cc', '45': '#cc00cc', '46': '#00cccc', '47': '#cccccc',
    '100': '#666666', '101': '#ff3333', '102': '#33ff33', '103': '#ffff33',
    '104': '#3333ff', '105': '#ff33ff', '106': '#33ffff', '107': '#ffffff',
};

interface Cell {
    char: string;
    fg: string;
    bg: string;
}

export class TerminalRenderer {
    private canvas: HTMLCanvasElement;
    private ctx: CanvasRenderingContext2D;
    private cols: number;
    private rows: number;
    private cellW = 0;
    private cellH = 0;
    private grid: Cell[][] = [];
    private cursorRow = 0;
    private cursorCol = 0;
    private currentFg = '#00cc00';
    private currentBg = '';
    private bold = false;

    constructor(canvas: HTMLCanvasElement, cols = 120, rows = 50) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d')!;
        this.cols = cols;
        this.rows = rows;
        this.initGrid();
        this.resize();
        window.addEventListener('resize', () => this.resize());
    }

    private initGrid() {
        this.grid = [];
        for (let r = 0; r < this.rows; r++) {
            const row: Cell[] = [];
            for (let c = 0; c < this.cols; c++) {
                row.push({ char: ' ', fg: '#00cc00', bg: '' });
            }
            this.grid.push(row);
        }
    }

    private resize() {
        const dpr = window.devicePixelRatio || 1;
        const rect = this.canvas.parentElement!.getBoundingClientRect();
        this.canvas.width = rect.width * dpr;
        this.canvas.height = rect.height * dpr;
        this.ctx.scale(dpr, dpr);

        // Calculate cell size from font
        const fontSize = Math.max(10, Math.floor(rect.height / this.rows));
        this.ctx.font = `${fontSize}px "Courier New", monospace`;
        const metrics = this.ctx.measureText('M');
        this.cellW = metrics.width;
        this.cellH = fontSize * 1.2;

        this.render();
    }

    clear() {
        this.initGrid();
        this.cursorRow = 0;
        this.cursorCol = 0;
        this.render();
    }

    /**
     * Process text with ANSI escape codes and write to the grid.
     */
    writeAnsi(text: string) {
        let i = 0;
        while (i < text.length) {
            if (text[i] === '\x1b' && text[i + 1] === '[') {
                // Parse ANSI escape
                i += 2;
                let code = '';
                while (i < text.length && text[i] !== 'm' && text[i] !== 'H'
                       && text[i] !== 'J' && text[i] !== 'K') {
                    code += text[i];
                    i++;
                }
                const terminator = text[i] || '';
                i++;

                if (terminator === 'm') {
                    this.applyStyle(code);
                } else if (terminator === 'H') {
                    // Cursor position: row;col
                    const parts = code.split(';');
                    this.cursorRow = Math.max(0, parseInt(parts[0] || '1') - 1);
                    this.cursorCol = Math.max(0, parseInt(parts[1] || '1') - 1);
                } else if (terminator === 'J') {
                    if (code === '2') this.clear();
                } else if (terminator === 'K') {
                    // Clear line
                    if (code === '2' || code === '') {
                        for (let c = 0; c < this.cols; c++) {
                            if (this.grid[this.cursorRow]) {
                                this.grid[this.cursorRow][c] = { char: ' ', fg: this.currentFg, bg: '' };
                            }
                        }
                    }
                }
            } else if (text[i] === '\n') {
                this.cursorRow++;
                this.cursorCol = 0;
                i++;
            } else if (text[i] === '\r') {
                this.cursorCol = 0;
                i++;
            } else {
                // Regular character
                if (this.cursorRow < this.rows && this.cursorCol < this.cols) {
                    if (this.grid[this.cursorRow]) {
                        this.grid[this.cursorRow][this.cursorCol] = {
                            char: text[i],
                            fg: this.currentFg,
                            bg: this.currentBg,
                        };
                    }
                    this.cursorCol++;
                }
                i++;
            }
        }
        this.render();
    }

    private applyStyle(code: string) {
        const parts = code.split(';');
        for (const part of parts) {
            if (part === '0' || part === '') {
                this.currentFg = '#00cc00';
                this.currentBg = '';
                this.bold = false;
            } else if (part === '1') {
                this.bold = true;
            } else if (part === '2') {
                this.currentFg = '#666666';
            } else if (ANSI_COLORS[part]) {
                this.currentFg = ANSI_COLORS[part];
            } else if (ANSI_BG_COLORS[part]) {
                this.currentBg = ANSI_BG_COLORS[part];
            }
        }
    }

    render() {
        const { ctx, cellW, cellH, cols, rows } = this;
        const rect = this.canvas.parentElement!.getBoundingClientRect();

        ctx.fillStyle = '#0a0a0a';
        ctx.fillRect(0, 0, rect.width, rect.height);

        const fontSize = Math.max(10, Math.floor(rect.height / rows));
        ctx.font = `${fontSize}px "Courier New", monospace`;
        ctx.textBaseline = 'top';

        for (let r = 0; r < rows; r++) {
            for (let c = 0; c < cols; c++) {
                const cell = this.grid[r]?.[c];
                if (!cell) continue;

                const x = c * cellW;
                const y = r * cellH;

                if (cell.bg) {
                    ctx.fillStyle = cell.bg;
                    ctx.fillRect(x, y, cellW + 1, cellH);
                }

                if (cell.char !== ' ') {
                    ctx.fillStyle = cell.fg;
                    ctx.fillText(cell.char, x, y + 1);
                }
            }
        }
    }
}
