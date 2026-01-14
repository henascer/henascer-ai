import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image, ImageOps
import pandas as pd
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import io

# 모델 선언 부분
model = genai.GenerativeModel(
    'nano-banana-pro-preview',
    safety_settings={
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
)


# 1. 페이지 설정
st.set_page_config(page_title="헤나세르 AI 스타일러", layout="centered")
st.title("✂️ 헤나세르 AI 가상 스타일링 (MVP)")

# 하단 푸터 및 메뉴 숨기기 CSS
hide_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            </style>
            """
st.markdown(hide_style, unsafe_allow_html=True)

# 2. 인증 설정
try:
    # Google Sheets 인증
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gspread_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    
    # 시트 열기
    sh = client.open_by_url(st.secrets["gsheets_url"])
    worksheet = sh.get_worksheet(0) # 첫 번째 탭
except Exception as e:
    st.error(f"설정 오류가 발생했습니다: {e}")
    st.stop()

# 제미나이 설정
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('nano-banana-pro-preview')

# 3. 메인 로직
with st.sidebar:
    st.header("🔑 멤버십 인증")
    access_key = st.text_input("액세스 키를 입력하세요 (대소문자 구분)", type="password")

if access_key:
    # 실시간 시트 데이터 확인
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    user_row = df[df['Access_Key'].astype(str) == access_key]

    if not user_row.empty:
        idx = user_row.index[0] # 시트에서의 행 위치
        remaining = int(user_row.iloc[0]['Remaining_Count'])
        
        if remaining > 0:
            st.success(f"✅ 인증 성공! 잔여 횟수: {remaining}회")
            
            # 1. 스타일 선택
            mode = st.selectbox("어떤 스타일을 시뮬레이션할까요?", ["헤어", "아우터", "이너"])
            
            st.markdown("---")

            # 2. 내 정면 사진 (Base) 섹션
            st.markdown("### 👤 <span style='font-size: 24px;'>내 정면 사진 (Base)</span>", unsafe_allow_html=True)
            # label_visibility="collapsed"를 추가하면 내부의 "본인의 정면 사진" 글자가 사라집니다.
            base_img = st.file_uploader("본인의 정면 사진", type=['jpg', 'png', 'jpeg'], label_visibility="collapsed")
            
            st.markdown("---")

            # 3. 합성할 헤어 사진 (Style) 섹션
            st.markdown("### 💇‍♂️ <span style='font-size: 24px;'>합성할 헤어 사진 (Style)</span>", unsafe_allow_html=True)
            
            # 안내 문구 및 예시 이미지
            st.info("💡 아래와 같은 '정면' 예시를 준비해주세요. (측면 사진은 불가해요)")
            st.image("example_front.jpg", width=250, caption="[합성이 잘 되는 정면 예시]")
            
            # 헤어 사진 업로드 창
            style_img = st.file_uploader("원하는 헤어 스타일 사진", type=['jpg', 'png', 'jpeg'], label_visibility="collapsed")

            st.markdown("---")

            # 4. 실행 버튼
            if base_img and style_img:
                if st.button(f"✨ {mode} 합성 시작하기 (1~2분)"):
                    with st.spinner("1~2분 정도 소요됩니다. 페이지를 이탈하거나 새로고침 하지 마세요."):
                        # 이미지 처리 및 합성 로직 시작
                        img_a = Image.open(base_img)
                        img_b = Image.open(style_img)
                                                
                        # 헤나세르님이 제안하신 프롬프트를 시스템 명령어로 구성
                        # 첫 번째 인자가 Image A, 두 번째 인자가 Image B임을 명시합니다.
                        prompt = f"""
                        URGENT: Strict head pose alignment. The nose and eyes in the output MUST be in the exact same pixel coordinates as Image A.
                        
                        [Role]: You are a Master AI Stylist specializing in photo-realistic Virtual Try-on.

                        [Input]:
                        - Image 1 (The FIRST image): BASE_IMAGE (The customer)
                        - Image 2 (The SECOND image): STYLE_IMAGE (The reference look)

                        [PRIME DIRECTIVE - CRITICAL]:
                        1. TARGET RECOGNITION: Focus ONLY on the human subject's head and body. Strictly ignore all mobile UI elements (status bars, notches, buttons, white/black bars) in both images.
                        2. IDENTITY ANCHOR: Use Image 1 as the absolute anchor. Do NOT rotate, tilt, or distort the face. The eye-line, nose position, and head angle must be 100% identical to Image 1.
                        3. STYLE EXTRACTION: Extract only the {mode} (texture, color, silhouette) from Image 2.

                        [Task]:
                        - "Surgically" replace ONLY the {mode} of the person in Image 1 with the style from Image 2.
                        - Head Pose Alignment: Ensure the new {mode} is naturally fitted onto the original head position of Image 1.
                        - Seamless Blending: The hairline and the area where the skin meets the {mode} must be perfectly blended with realistic shadows.
                        - Preservation: Keep the original facial features (eyebrows, eyes, skin texture), background, and clothing of Image 1 untouched.

                        [Important Rules]:
                        - The result must be a SINGLE integrated photo, NOT a side-by-side comparison.
                        - The person's identity and facial proportions must remain 100% recognizable as the person in Image 1.
                        - No text, no descriptions, no watermarks. Output ONLY the resulting image.
                        """
                        
                        try:
                            # 1. AI에게 이미지 생성 요청
                            response = model.generate_content([prompt, img_a, img_b])
                            
                            found_image = False
                            image_data = None # 이미지 데이터를 저장할 변수

                            if response.candidates:
                                for part in response.candidates[0].content.parts:
                                    if part.inline_data:
                                        # [수정] 바로 화면에 띄우지 않고, 데이터만 변수에 저장합니다.
                                        image_data = part.inline_data.data
                                        found_image = True
                                        break # 이미지를 찾았으면 루프 종료
                            
                            if found_image and image_data:
                                # --- [1. 워터마크 합성 로직 시작] ---
                                try:
                                    # AI가 만든 원본 이미지 로드
                                    base_image = Image.open(io.BytesIO(image_data)).convert("RGBA")
                                    
                                    # 로고 이미지 로드
                                    logo = Image.open("logo.png").convert("RGBA")

                                    # 로고 크기 조절
                                    target_width = int(base_image.width * 0.2)
                                    aspect_ratio = logo.height / logo.width
                                    target_height = int(target_width * aspect_ratio)
                                    logo_resized = logo.resize((target_width, target_height), Image.LANCZOS)

                                    # 로고 위치 계산
                                    padding = 20
                                    position = (base_image.width - logo_resized.width - padding, base_image.height - logo_resized.height - padding)

                                    # 합성
                                    watermark_layer = Image.new('RGBA', base_image.size, (0,0,0,0))
                                    watermark_layer.paste(logo_resized, position, mask=logo_resized)
                                    display_image = Image.alpha_composite(base_image, watermark_layer)

                                except FileNotFoundError:
                                    # 로고 파일이 없으면 원본을 그대로 보여줌
                                    st.warning("⚠️ 로고 파일(logo.png)을 찾을 수 없어 워터마크 없이 출력합니다.")
                                    display_image = Image.open(io.BytesIO(image_data))
                                
                                # --- [2. 최종 결과물 딱 한 번만 출력] ---
                                st.image(display_image, caption="✨ 헤나세르 AI 스타일링 결과", use_column_width=True)

                                # 2-1. [신규] 하단 고정 주의 문구 (회색의 작은 글씨로 깔끔하게 배치)
                                st.markdown("""
                                    <div style='text-align: center; color: #808080; font-size: 13px; line-height: 1.6; margin-top: 10px;'>
                                        이 결과는 스타일 방향성을 보기 위한<br>
                                        AI 시뮬레이션입니다.<br>
                                        실제와 100% 일치하지 않을 수 있습니다.
                                    </div>
                                """, unsafe_allow_html=True)

                                # 2-2. [신규] 좋아요 피드백 섹션
                                st.write("")
                                col_like, col_empty = st.columns([1, 1])
                                with col_like:
                                    if st.button("👍 이 결과가 마음에 드시나요? (Like)"):
                                        try:
                                            # 1. 현재 '좋아요' 값 가져오기 (D열은 4번째 열)
                                            # 만약 셀이 비어있으면 0으로 취급합니다.
                                            current_likes_val = worksheet.cell(idx + 2, 4).value
                                            current_likes = int(current_likes_val) if current_likes_val and str(current_likes_val).isdigit() else 0
                                            
                                            # 2. 값 1 증가시켜 업데이트
                                            worksheet.update_cell(idx + 2, 4, current_likes + 1)
                                            
                                            st.toast("피드백 감사합니다! 데이터가 안전하게 기록되었습니다. 😊")
                                        except Exception as e:
                                            st.error(f"피드백 기록 중 오류가 발생했습니다: {e}")

                                st.markdown("---")

                                # 3. 캡처 안내 문구
                                st.success("✅ 합성이 완료되었습니다!")
                                st.markdown("""
                                    ### 📸 **지금 화면을 캡쳐하세요!**
                                    <div style='background-color:#f0f2f6; padding:15px; border-radius:10px;'>
                                    미용실 방문 시 디자이너에게 이 사진을 보여주시면 상담이 훨씬 수월해집니다.😉
                                    </div>
                                    <br>
                                    """, unsafe_allow_html=True)

                                # 횟수 차감 및 효과
                                worksheet.update_cell(idx + 2, 3, remaining - 1)
                                st.balloons()
                                
                            else:
                                st.error("AI가 이미지를 생성하지 못했습니다. 다시 시도해 주세요.")
                                if hasattr(response, 'text'): st.write(response.text)

                        except Exception as e:
                            st.error(f"합성 엔진 오류: {e}")
        else:
            st.error("잔여 횟수가 0입니다. 충전이 필요합니다.")
    else:
        st.error("잘못된 키입니다.")
else:
    st.info("좌측 상단의 ' >> '를 눌러서 키를 입력해주세요.")