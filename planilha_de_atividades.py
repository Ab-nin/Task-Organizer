import numpy as np
import streamlit as st
import pandas as pd
import plotly.express as px # type: ignore
from datetime import datetime, timezone as dt_timezone, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from cryptography.fernet import Fernet
import base64
from pytz import timezone as pytz_timezone

# Configuração inicial da página
st.set_page_config(
    page_title='Planilha de Atividades do Abner',
    page_icon='📅',
    layout="wide"
)

# Configuração de fuso horário
TIMEZONE = pytz_timezone('America/Sao_Paulo')

# Função para enviar email (mantida igual)
def send_daily_reminder(task_details):
    try:
        smtp_server = 'smtp.gmail.com'
        port = 587
        
        message = MIMEMultipart()
        message['From'] = st.secrets["email"]["sender"]
        message['To'] = task_details['Email do Responsável'] if 'Email do Responsável' in task_details else task_details.get('Email Responsável', st.session_state.email_config['receiver_email'])
        message['Subject'] = f'Lembrete Diário: {task_details["Tarefa"]}'

        body = f"""
        <h3>Lembrete de Tarefa</h3>
        <p><strong>Tarefa:</strong> {task_details['Tarefa']}</p>
        <p><strong>Descrição:</strong> {task_details['Descrição']}</p>
        <p><strong>Período:</strong> {task_details['Início'].strftime('%d/%m/%Y')} - {task_details['Fim'].strftime('%d/%m/%Y')}</p>
        <p><strong>Dias Restantes:</strong> {(task_details['Fim'] - datetime.now(TIMEZONE).date()).days} dias</p>
        <p>Por favor, não se esqueça de atualizar o progresso desta tarefa.</p>
        <hr>
        <p>Este é um lembrete automático enviado diariamente até a data de conclusão.</p>
        """

        message.attach(MIMEText(body, 'html'))
        
        server = smtplib.SMTP(smtp_server, port)
        server.starttls()
        server.login(st.secrets["email"]["sender"], st.secrets["email"]["password"])
        server.send_message(message)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Erro ao enviar email: {str(e)}")
        return False
    
    
# Função modificada para verificação de horário
def check_and_send_reminders():
    now = datetime.now(TIMEZONE).date()
    emails_sent = 0
    errors = 0
    
    for idx, task in st.session_state.tasks.iterrows():
        try:
            if task['Início'] <= now <= task['Fim']:
                last_sent_key = f"último_lembrete_{idx}"
                if last_sent_key not in st.session_state:
                    st.session_state[last_sent_key] = None
                
                last_sent = st.session_state[last_sent_key]
                
                if last_sent is None or last_sent.date() < now:
                    responsavel = task['Responsável']
                    email_responsavel = (
                        st.session_state.responsaveis_emails.get(responsavel, 
                        st.session_state.email_config['receiver_email'])
                        if 'Email Responsável' not in task
                        else task['Email Responsável']
                    )
                    
                    task_details = task.to_dict()
                    task_details['Email do Responsável'] = email_responsavel
                    
                    if email_responsavel and send_reminder_email(
                        task_details['Tarefa'],
                        task_details['Descrição'],
                        f"{task_details['Início']} - {task_details['Fim']}",
                        email_responsavel
                    ):
                        st.session_state[last_sent_key] = datetime.now(TIMEZONE)
                        emails_sent += 1
        except Exception as e:
            errors += 1

    return emails_sent, errors

# Implementação do check_daily_reminders com horário específico
def check_daily_reminders():
    if 'last_daily_reminder_check' not in st.session_state:
        st.session_state.last_daily_reminder_check = None
    
    now = datetime.now(TIMEZONE)
    target_time = now.replace(hour=7, minute=0, second=0, microsecond=0)
    
    # Verifica se já passou das 7h e se é a primeira verificação do dia
    if now >= target_time and (
        st.session_state.last_daily_reminder_check is None or
        st.session_state.last_daily_reminder_check.date() < now.date()
    ):
        emails_sent, errors = check_and_send_reminders()
        st.session_state.last_daily_reminder_check = now
        
        if emails_sent > 0:
            st.toast(f"✅ {emails_sent} lembretes enviados às {now.strftime('%H:%M')}")
        return emails_sent > 0
    
    return False


# Função para criar uma chave de criptografia
def get_key():
    if 'crypto_key' not in st.session_state:
        st.session_state.crypto_key = Fernet.generate_key()
    return st.session_state.crypto_key

# Funções para criptografia
def encrypt_text(text):
    if not text:
        return ""
    f = Fernet(get_key())
    return base64.urlsafe_b64encode(f.encrypt(text.encode())).decode()

def decrypt_text(encrypted_text):
    if not encrypted_text:
        return ""
    try:
        f = Fernet(get_key())
        return f.decrypt(base64.urlsafe_b64decode(encrypted_text)).decode()
    except:
        return ""

# Configuração de email (com armazenamento seguro)
if 'email_config' not in st.session_state:
    st.session_state.email_config = {
        'sender_email': '',
        'password_encrypted': '',
        'receiver_email': ''
    }

# Criando um DataFrame vazio para a organização das tarefas
if 'tasks' not in st.session_state:
    st.session_state.tasks = pd.DataFrame(
        columns=['Tarefa', 'Descrição', 'Início', 'Fim', 'Responsável', 'Email Responsável']
    )

# Carregar backup se existir
if 'data_loaded' not in st.session_state:
    try:
        backup_df = pd.read_csv('backup_tarefas.csv')
        if not backup_df.empty and all(col in backup_df.columns for col in ['Tarefa', 'Descrição', 'Início', 'Fim', 'Responsável']):
            # Converter strings de data para objetos datetime
            backup_df['Início'] = pd.to_datetime(backup_df['Início']).dt.date
            backup_df['Fim'] = pd.to_datetime(backup_df['Fim']).dt.date
            st.session_state.tasks = backup_df
            st.session_state.data_loaded = True
    except:
        st.session_state.data_loaded = True

# Função para salvar backup
def save_backup():
    if not st.session_state.tasks.empty:
        st.session_state.tasks.to_csv('backup_tarefas.csv', index=False)

# Função para enviar email
def send_reminder_email(task, task_description, date, receiver_email):
    if not st.session_state.email_config['sender_email'] or not st.session_state.email_config['password_encrypted']:
        st.warning("Configure seu email antes de enviar lembretes!")
        return False
    
    try:
        password = decrypt_text(st.session_state.email_config['password_encrypted'])
        
        # Tentar primeiro com TLS
        try:
            smtp_server = "smtp.gmail.com"
            port = 587
            
            message = MIMEMultipart()
            message["From"] = st.session_state.email_config['sender_email']
            message["To"] = receiver_email
            message["Subject"] = f"Lembrete de Tarefa: {task}"
            
            # Corpo do email em HTML para melhor formatação
            body = f"""
            <html>
            <body>
                <h3>Lembrete de Tarefa</h3>
                <p><b>Tarefa:</b> {task}</p>
                <p><b>Descrição:</b> {task_description}</p>
                <p><b>Data:</b> {date}</p>
                <hr>
                <p>Este é um lembrete automático do seu Sistema de Gerenciamento de Tarefas.</p>
            </body>
            </html>
            """
            
            message.attach(MIMEText(body, "html"))
            
            server = smtplib.SMTP(smtp_server, port)
            server.starttls()
            server.login(st.session_state.email_config['sender_email'], password)
            server.send_message(message)
            server.quit()
            return True
        
        # Fallback para SSL se TLS falhar
        except:
            smtp_server = "smtp.gmail.com"
            port = 465
            
            message = MIMEMultipart()
            message["From"] = st.session_state.email_config['sender_email']
            message["To"] = receiver_email
            message["Subject"] = f"Lembrete de Tarefa: {task}"
            
            body = f"""
            <html>
            <body>
                <h3>Lembrete de Tarefa</h3>
                <p><b>Tarefa:</b> {task}</p>
                <p><b>Descrição:</b> {task_description}</p>
                <p><b>Data:</b> {date}</p>
                <hr>
                <p>Este é um lembrete automático do seu Sistema de Gerenciamento de Tarefas.</p>
            </body>
            </html>
            """
            
            message.attach(MIMEText(body, "html"))
            
            import ssl
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
                server.login(st.session_state.email_config['sender_email'], password)
                server.send_message(message)
            return True
            
    except Exception as e:
        st.error(f"Erro ao enviar email: {str(e)}")
        return False

# Criação de abas para melhor organização
tab1, tab2, tab3, tab4 = st.tabs(["📊 Gráfico de Gantt", "📝 Gerenciar Tarefas", "📧 Lembretes", "⚙️ Configurações"])

# Aba de Configurações
with tab4:
    st.header('Configurações de Email')
    st.warning("⚠️ Use uma 'Senha de App' do Google em vez de sua senha normal para maior segurança.")
    st.info("Para criar uma senha de app: Acesse sua conta Google → Segurança → Autenticação de duas etapas → Senhas de app")
    
    st.session_state.email_config['sender_email'] = st.text_input(
        'Email Remetente (Gmail)',
        value=st.session_state.email_config['sender_email']
    )
    
    # Usando password criptografado
    password_input = st.text_input(
        'Senha do App Gmail',
        type='password'
    )
    
    if password_input:
        # Só atualiza se houver alguma entrada
        st.session_state.email_config['password_encrypted'] = encrypt_text(password_input)
    
    st.session_state.email_config['receiver_email'] = st.text_input(
        'Email Padrão para Receber Lembretes',
        value=st.session_state.email_config['receiver_email']
    )
    
    if st.button('Testar Configuração de Email'):
        if send_reminder_email("Teste de Configuração", "Este é um email de teste.", 
                             datetime.now(dt_timezone.utc).date(), 
                             st.session_state.email_config['receiver_email']):
            st.success('✅ Email enviado com sucesso!')
        else:
            st.error('❌ Falha ao enviar email. Verifique as configurações.')

    # Novo elemento para mostrar o status do agendamento
    if 'last_daily_reminder_check' in st.session_state and st.session_state.last_daily_reminder_check:
        next_check = st.session_state.last_daily_reminder_check + timedelta(days=1)
        next_check = next_check.replace(hour=7, minute=0)
        st.info(f"**Próximo envio automático:** {next_check.strftime('%d/%m/%Y às %H:%M')}")
    else:
        st.info("**Próximo envio automático:** 7:00 do próximo dia útil")

# Nova aba para gerenciar lembretes
with tab3:
    st.header('Configuração de Lembretes Diários')
    st.markdown("""
    ### Lembretes Diários Automáticos
    
    Os lembretes são enviados automaticamente uma vez por dia para os responsáveis por tarefas que estão em andamento (dentro do período entre a data de início e fim).
    """)
    
    # Dicionário para armazenar emails dos responsáveis
    if 'responsaveis_emails' not in st.session_state:
        st.session_state.responsaveis_emails = {}
    
    st.subheader("Cadastrar Emails dos Responsáveis")
    
    # Obtém lista única de responsáveis
    if not st.session_state.tasks.empty:
        responsaveis = sorted(st.session_state.tasks['Responsável'].unique())
        
        for resp in responsaveis:
            email_resp = st.text_input(
                f"Email de {resp}",
                value=st.session_state.responsaveis_emails.get(resp, ""),
                key=f"email_{resp}"
            )
            
            if email_resp:
                st.session_state.responsaveis_emails[resp] = email_resp
    
    st.subheader("Verificação Manual de Lembretes")
    
    if st.button("Enviar Lembretes Agora"):
        emails_sent, errors = check_and_send_reminders()
        if emails_sent > 0:
            st.success(f"✅ {emails_sent} lembretes enviados com sucesso!")
        else:
            st.info("Nenhum lembrete precisava ser enviado agora.")
    
    st.subheader("Status dos Lembretes")
    
    if 'last_daily_reminder_check' in st.session_state and st.session_state.last_daily_reminder_check:
        st.info(f"Última verificação: {st.session_state.last_daily_reminder_check.strftime('%d/%m/%Y %H:%M:%S')}")
    else:
        st.info("Ainda não foram enviados lembretes nesta sessão.")
        
    # Mostrar tarefas com lembretes ativos
    st.subheader("Tarefas com Lembretes Ativos")
    
    now = datetime.now(TIMEZONE).date()
    active_tasks = st.session_state.tasks[(st.session_state.tasks['Início'] <= now) & (now <= st.session_state.tasks['Fim'])]
    
    if not active_tasks.empty:
        for i, task in active_tasks.iterrows():
            st.markdown(f"""
            **{task['Tarefa']}** - Responsável: {task['Responsável']}  
            *De {task['Início']} até {task['Fim']}*
            """)
    else:
        st.info("Não há tarefas ativas no momento para envio de lembretes.")

    st.subheader("Status do Agendamento")
    cols = st.columns(2)
    with cols[0]:
        if 'last_daily_reminder_check' in st.session_state and st.session_state.last_daily_reminder_check:
            st.metric("Último envio", st.session_state.last_daily_reminder_check.strftime('%d/%m/%Y %H:%M'))
        else:
            st.metric("Último envio", "Nunca")
    
    with cols[1]:
        next_check = datetime.now(TIMEZONE).replace(hour=7, minute=0) + timedelta(days=1)
        st.metric("Próximo envio previsto", next_check.strftime('%d/%m/%Y %H:%M'))


# Aba de Gerenciar Tarefas
with tab2:
    st.header('Adicionar Nova Tarefa')
    
    # Formulário para adicionar tarefas
    with st.form("add_task_form"):
        task_name = st.text_input('Nome da Tarefa')
        task_description = st.text_area('Descrição da Tarefa')
        
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input('Data de Início')
        with col2:
            end_date = st.date_input('Data Final')
        
        owner = st.text_input('Responsável')
        
        # Adicionando campo de email específico para a tarefa
        owner_email = st.text_input(
            'Email do Responsável (opcional)',
            help="Se não preenchido, usará o email cadastrado na aba Lembretes ou o email padrão."
        )
        
        submitted = st.form_submit_button("Adicionar Tarefa")
        
        if submitted:
            # Validação de datas
            if end_date < start_date:
                st.error("⚠️ Data final não pode ser anterior à data de início!")
            elif not task_name:
                st.error("⚠️ Nome da tarefa não pode estar vazio!")
            else:
                new_task = pd.DataFrame([[task_name, task_description, start_date, end_date, owner, owner_email]],
                                       columns=['Tarefa', 'Descrição', 'Início', 'Fim', 'Responsável', 'Email Responsável'])
                st.session_state.tasks = pd.concat([st.session_state.tasks, new_task], ignore_index=True)
                save_backup()
                st.success(f"✅ Tarefa '{task_name}' adicionada com sucesso!")
    
    # Gerenciamento de tarefas existentes
    st.header('Tarefas Existentes')

    if st.session_state.tasks.empty:
        st.info("Nenhuma tarefa cadastrada. Adicione tarefas no formulário acima.")
    else:
        # Filtros
        col1, col2 = st.columns(2)
        with col1:
            filter_responsible = st.multiselect(
                "Filtrar por Responsável", 
                options=sorted(st.session_state.tasks['Responsável'].unique())
            )

        with col2:
            search_term = st.text_input("Pesquisar tarefa", "")

        # Aplicar filtros
        filtered_df = st.session_state.tasks.copy()

        if filter_responsible:
            filtered_df = filtered_df[filtered_df['Responsável'].isin(filter_responsible)]

        if search_term:
            mask = (
                filtered_df['Tarefa'].str.contains(search_term, case=False) | 
                filtered_df['Descrição'].str.contains(search_term, case=False)
            )
            filtered_df = filtered_df[mask]

        # Criando uma nova coluna para botões de exclusão
        for i in range(len(filtered_df)):
            cols = st.columns([2, 3, 2, 2, 2, 3, 1])
            cols[0].write(filtered_df.iloc[i]['Tarefa'])
            cols[1].write(filtered_df.iloc[i]['Descrição'])
            cols[2].write(filtered_df.iloc[i]['Início'])
            cols[3].write(filtered_df.iloc[i]['Fim'])
            cols[4].write(filtered_df.iloc[i]['Responsável'])
            cols[5].write(filtered_df.iloc[i].get('Email Responsável', ''))

            if cols[6].button("❌", key=f"delete_{i}"):
                task_to_remove = filtered_df.iloc[i]['Tarefa']
                st.session_state.tasks = st.session_state.tasks[st.session_state.tasks['Tarefa'] != task_to_remove]
                save_backup()
                st.rerun()

        
        # Editor de dados experimental
        st.subheader("Editar Tarefas")
        edited_df = st.data_editor(
            filtered_df,
            column_config={
                "Tarefa": st.column_config.TextColumn("Tarefa"),
                "Descrição": st.column_config.TextColumn("Descrição"),
                "Início": st.column_config.DateColumn("Início"),
                "Fim": st.column_config.DateColumn("Fim"),
                "Responsável": st.column_config.TextColumn("Responsável"),
                "Email Responsável": st.column_config.TextColumn("Email Responsável")
            },
            hide_index=True,
            num_rows="dynamic",
            key="task_editor"
        )
        
        if st.button("Salvar Alterações"):
            st.session_state.tasks = edited_df
            save_backup()
            st.success("✅ Alterações salvas com sucesso!")
        
        # Botão para limpar todas as tarefas
        if st.button('Limpar Todas as Tarefas'):
            confirm = st.checkbox('⚠️ Confirma a exclusão de TODAS as tarefas? Esta ação não pode ser desfeita!')
            if confirm:
                st.session_state.tasks = pd.DataFrame(
                    columns=['Tarefa', 'Descrição', 'Início', 'Fim', 'Responsável', 'Email Responsável']
                )
                save_backup()
                st.success('🗑️ Todas as tarefas foram removidas!')


# Aba do Gráfico de Gantt
with tab1:
    st.title('Gráfico de Gantt Interativo 📊')
    
    if not st.session_state.tasks.empty:
        # Opções de personalização do gráfico
        st.subheader("Opções de Visualização")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            bar_thickness = st.slider("Espessura das barras", 0.1, 1.0, 0.3, 0.1)
        
        with col2:
            sort_option = st.selectbox(
                "Ordenar por",
                ["Início", "Fim", "Tarefa", "Responsável"]
            )
        
        with col3:
            color_option = st.selectbox(
                "Colorir por",
                ["Responsável", "Período"]
            )
        
        # Ordenar o DataFrame
        df_sorted = st.session_state.tasks.sort_values(by=sort_option)
        
        # Definir a coluna de cores
        color_by = "Responsável" if color_option == "Responsável" else None
        
        # Criando gráfico com a Plotly
        fig = px.timeline(
            df_sorted,
            x_start='Início',
            x_end='Fim',
            y='Tarefa',
            color=color_by,
            hover_data=['Descrição'],
            title='Linha de Tempo de Tarefas'
        )

        # Personalizando o layout
        fig.update_yaxes(autorange='reversed')
        fig.update_layout(
            height=600,
            xaxis_title='Período',
            yaxis_title='Tarefas',
            hovermode='closest',
            bargap=0.2,
            bargroupgap=0.1
        )

        # Atualizando o template para barras mais finas
        fig.update_traces(width=bar_thickness)

        st.plotly_chart(fig, use_container_width=True)
        
        # Mostrar detalhes ao passar o mouse
        st.info("ℹ️ Passe o mouse sobre as barras para ver mais detalhes da tarefa.")
        
        # Enviar lembretes
        st.subheader("Enviar Lembretes")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            task_for_reminder = st.selectbox(
                "Selecione a tarefa",
                options=st.session_state.tasks['Tarefa'].tolist()
            )
        
        selected_task = st.session_state.tasks[st.session_state.tasks['Tarefa'] == task_for_reminder].iloc[0]
        
        with col2:
            st.markdown(f"**Responsável:** {selected_task['Responsável']}")
            st.markdown(f"**Data início:** {selected_task['Início']}")
        
        with col3:
            if st.button('📧 Enviar Lembrete'):
                email_to_use = selected_task.get('Email Responsável', '')
                if not email_to_use:
                    email_to_use = st.session_state.responsaveis_emails.get(
                        selected_task['Responsável'], 
                        st.session_state.email_config['receiver_email']
                    )
                
                if send_reminder_email(
                    selected_task['Tarefa'], 
                    selected_task['Descrição'],
                    f"{selected_task['Início']} - {selected_task['Fim']}", 
                    email_to_use
                ):
                    st.success('✅ Lembrete enviado com sucesso!')
    else:
        st.info('Adicione tarefas na aba "Gerenciar Tarefas" para visualizar o gráfico.')
        
        # Exemplo de visualização
        st.subheader("Exemplo de Visualização")
        
        # Dados de exemplo
        example_df = pd.DataFrame([
            ["Tarefa 1", "Descrição da tarefa 1", datetime(2024, 2, 1).date(), datetime(2024, 2, 10).date(), "João"],
            ["Tarefa 2", "Descrição da tarefa 2", datetime(2024, 2, 5).date(), datetime(2024, 2, 15).date(), "Maria"],
            ["Tarefa 3", "Descrição da tarefa 3", datetime(2024, 2, 8).date(), datetime(2024, 2, 20).date(), "João"]
        ], columns=['Tarefa', 'Descrição', 'Início', 'Fim', 'Responsável'])
        
        fig = px.timeline(
            example_df,
            x_start='Início',
            x_end='Fim',
            y='Tarefa',
            color='Responsável',
            title='Exemplo de Gráfico de Gantt (Dados Fictícios)'
        )
        
        fig.update_yaxes(autorange='reversed')
        fig.update_layout(
            height=400,
            bargap=0.2
        )
        
        fig.update_traces(width=0.3)
        
        st.plotly_chart(fig, use_container_width=True)

# Verifica e envia lembretes diários
check_daily_reminders()

# Rodapé com informações de ajuda
st.markdown("---")
with st.expander("ℹ️ Ajuda e Instruções"):
    st.markdown("""
    ### Como usar este aplicativo
    
    **1. Adicionar Tarefas:**
    - Vá para a aba "Gerenciar Tarefas"
    - Preencha o formulário com nome, descrição, datas e responsável
    - Clique em "Adicionar Tarefa"
    
    **2. Visualizar Gráfico:**
    - Acesse a aba "Gráfico de Gantt"
    - Ajuste a espessura das barras com o controle deslizante
    - Passe o mouse sobre as barras para ver detalhes
    
    **3. Configurar Lembretes:**
    - Na aba "Configurações", adicione seus dados de e-mail
    - Use uma "Senha de App" do Google para maior segurança
    - Cadastre emails dos responsáveis na aba "Lembretes"
    - Os lembretes são enviados automaticamente uma vez por dia
    
    **4. Gerenciar Tarefas Existentes:**
    - Edite tarefas diretamente na tabela interativa
    - Use filtros para encontrar tarefas específicas
    - Clique em "Salvar Alterações" após editar
    
    **Dicas:**
    - Os dados são salvos automaticamente em um arquivo CSV
    - Para receber lembretes, certifique-se de configurar corretamente seu e-mail
    - Use a pesquisa para encontrar tarefas rapidamente
    """)

# Salvar backup ao final da execução
save_backup()