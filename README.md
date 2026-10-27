# Cartão de Ponto Digital

Sistema web de ponto com reconhecimento facial. Flask + PostgreSQL + OpenCV (YuNet detecta, SFace reconhece).

**Admin:** cadastra funcionários com rosto, vê todos os registros, gera espelho de ponto (imprimir/PDF e CSV), vê documentos e responde mensagens.
**Funcionário:** bate as 4 batidas (entrada, saída almoço, volta almoço, saída) com validação facial, envia documentos e mensagens.

## Publicar no Render
1. Crie um repositório no GitHub e envie esta pasta (`git init && git add . && git commit -m ponto && git push`).
2. No Render: **New > Blueprint**, escolha o repositório. O `render.yaml` cria o banco e o serviço web.
3. Aguarde o build (baixa ~40 MB de modelos). A URL será `https://ponto-digital.onrender.com` (ou similar), já com HTTPS, necessário para a câmera.
4. Entre em **ponto-digital > Environment** e copie o valor de `ADMIN_PASSWORD`. Login: matrícula `admin` + essa senha.
5. Cadastre os funcionários (aba Funcionários, com captura do rosto) e peça que acessem a URL no celular ou PC.

Plano free: o serviço hiberna sem uso (primeira abertura demora) e o banco free pode expirar. Para produção use planos pagos (web *starter* ou superior; 512 MB de RAM bastam).

## Rodar local
```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && python download_models.py
python app.py   # http://localhost:5000, admin / admin123
```

## Variáveis
| Nome | Função |
|---|---|
| `SECRET_KEY` | assina a sessão (gerada pelo Render) |
| `ADMIN_MAT` / `ADMIN_PASSWORD` | admin criado no primeiro start |
| `TZ_NAME` | fuso para dias e espelho (padrão America/Sao_Paulo) |
| `FACE_THRESHOLD` | similaridade mínima (0.45 padrão; suba para 0.5+ para ser mais rígido) |

## Reconhecimento facial
O navegador envia o quadro; o servidor detecta o maior rosto (YuNet), gera um vetor de 128 números (SFace) e compara com os vetores cadastrados do próprio funcionário (similaridade de cosseno). Guardamos apenas os vetores e uma miniatura de 80 px de cada batida.

## Atenção
- **LGPD:** biometria é dado pessoal sensível. Colete consentimento por escrito, defina prazo de retenção e restrinja o acesso ao admin.
- **Prova de vida:** não incluída; uma foto impressa ou na tela pode tentar enganar. Para ambientes de risco, adicione detecção de vida ou batida em tablet supervisionado.
- **Validade legal:** para ponto eletrônico oficial (Portaria MTP 671/2021) são exigidos comprovante de registro, AFD e demais requisitos. Consulte um contador ou advogado trabalhista.
- **Documentos** ficam no banco (até 8 MB por envio); para muito volume, migre para S3/R2.
